"""Lock-contended compression no-ops must soft-DEFER, never exhaust (#49874).

On main before this fix, nothing on the automatic compression paths consumed
the #69870 lock-skip signal (``agent._compression_skipped_due_to_lock``):

* a lock-loser preflight/pre-API no-op counted as "insufficient progress",
* the oversized request went to the provider anyway, and
* the lock-contended 413/overflow retry burned ``compression_attempts`` to
  the cap and returned ``compression_exhausted`` — which the gateway answers
  with a full session auto-reset (#9893/#35809).

A temporary lock defer misclassified as exhaustion == session wipe.

These tests pin the fix: when a compression pass returns its input unchanged
AND the type-pinned lock-skip flag is set, the attempt is refunded and the
turn ends (when it cannot proceed) with a soft ``compression_deferred``
result distinct from ``compression_exhausted``.

Salvaged from PR #49874 (@helix4u), rebuilt on the landed #69870 signal.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.conversation_compression import compression_skipped_due_to_lock
from agent.turn_preflight import PreflightGateVerdict, run_preflight_compression
from run_agent import AIAgent


LOCK_HOLDER = "pid=4242:tid=1:agent=deadbeef:nonce=abcd1234"


# ---------------------------------------------------------------------------
# Helpers (mirrors tests/agent/test_413_compression.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_compression_sleep(monkeypatch):
    import time as _time

    monkeypatch.setattr(_time, "sleep", lambda *_a, **_k: None)
    from agent import retry_utils as _retry_utils
    monkeypatch.setattr(_retry_utils, "jittered_backoff", lambda *a, **k: 0.0)


def _make_tool_defs(*names: str) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": n,
                "description": f"{n} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for n in names
    ]


def _mock_response(content="Hello", finish_reason="stop"):
    msg = SimpleNamespace(
        content=content,
        tool_calls=None,
        reasoning_content=None,
        reasoning=None,
    )
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    resp = SimpleNamespace(choices=[choice], model="test/model")
    resp.usage = None
    return resp


def _make_413_error(message="Request entity too large"):
    err = Exception(message)
    err.status_code = 413
    return err


def _make_overflow_error():
    return Exception(
        "Error code: 400 - {'type': 'error', 'error': {'type': "
        "'invalid_request_error', 'message': 'prompt is too long: "
        "233153 tokens > 200000 maximum'}}"
    )


@pytest.fixture()
def agent():
    with (
        patch("model_tools.get_tool_definitions", return_value=_make_tool_defs("web_search")),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        a = AIAgent(
            api_key="test-key-1234567890",
            base_url="https://openrouter.ai/api/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )
        a.client = MagicMock()
        a._cached_system_prompt = "You are helpful."
        a._use_prompt_caching = False
        a.tool_delay = 0
        a.compression_enabled = True
        a.save_trajectories = False
        return a


_PREFILL = [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"},
]


def _lock_skipping_compress(agent, *, holder=LOCK_HOLDER):
    """A compress double that no-ops because 'another path holds the lock'.

    Mirrors the real ``compress_context`` lock-contended abort: returns the
    INPUT list object unchanged and sets the #69870 lock-skip signal.
    """

    def _compress(messages, _system_message, **_kwargs):
        agent._compression_skipped_due_to_lock = holder
        return messages, "You are helpful."

    return _compress


def _plain_noop_compress(agent):
    """A compress double that no-ops WITHOUT lock contention (real no-progress)."""

    def _compress(messages, _system_message, **_kwargs):
        agent._compression_skipped_due_to_lock = None
        return messages, "You are helpful."

    return _compress


# ---------------------------------------------------------------------------
# Type-pinned signal read (MagicMock test-double immunity)
# ---------------------------------------------------------------------------


class TestLockSkipSignalTypePin:
    def test_true_and_holder_string_are_lock_skips(self):
        a = SimpleNamespace(_compression_skipped_due_to_lock=True)
        assert compression_skipped_due_to_lock(a) is True
        a = SimpleNamespace(_compression_skipped_due_to_lock=LOCK_HOLDER)
        assert compression_skipped_due_to_lock(a) is True

    def test_none_and_missing_are_not_lock_skips(self):
        assert compression_skipped_due_to_lock(
            SimpleNamespace(_compression_skipped_due_to_lock=None)
        ) is False
        assert compression_skipped_due_to_lock(SimpleNamespace()) is False


    def test_truthy_non_true_non_str_values_are_not_lock_skips(self):
        for junk in (1, 1.0, ["holder"], {"holder": True}, object(), MagicMock()):
            a = SimpleNamespace(_compression_skipped_due_to_lock=junk)
            assert compression_skipped_due_to_lock(a) is False, junk


# ---------------------------------------------------------------------------
# 413 handler: lock-contended no-op → soft defer, no exhaustion
# ---------------------------------------------------------------------------


class TestLockContended413Defer:
    def test_lock_contended_413_returns_compression_deferred(self, agent):
        """A 413 whose compression pass lost the lock must end the turn as a
        soft ``compression_deferred`` — never ``compression_exhausted``."""
        agent.client.chat.completions.create.side_effect = _make_413_error()

        with (
            patch.object(
                agent, "_compress_context",
                side_effect=_lock_skipping_compress(agent),
            ) as mock_compress,
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            result = agent.run_conversation("hello", conversation_history=list(_PREFILL))

        mock_compress.assert_called_once()
        assert result.get("compression_deferred") is True
        assert not result.get("compression_exhausted")
        # Soft defer: transient, retry-next-message semantics — the gateway
        # persists the user turn (failed=False) and never auto-resets.
        assert result.get("failed") is False
        assert result.get("completed") is False
        assert result.get("partial") is True


    def test_unconfirmed_lock_skip_true_also_defers(self, agent):
        """``_compression_skipped_due_to_lock = True`` (holder unconfirmed —
        ``try_acquire`` swallowed a sqlite error) is still a lock skip."""
        agent.client.chat.completions.create.side_effect = _make_413_error()

        with (
            patch.object(
                agent, "_compress_context",
                side_effect=_lock_skipping_compress(agent, holder=True),
            ),
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            result = agent.run_conversation("hello", conversation_history=list(_PREFILL))

        assert result.get("compression_deferred") is True
        assert not result.get("compression_exhausted")




# ---------------------------------------------------------------------------
# Pre-API gate: a lock-skipped pass must not burn the shared attempt budget
# ---------------------------------------------------------------------------


class TestPreApiLockDeferDoesNotBurnBudget:
    def test_lock_loser_turn_recovers_after_lock_release(self, agent):
        """End-to-end shape of the live bug at cap=1:

        1. Pre-API pressure gate fires; the compression pass loses the lock
           (no-op + lock-skip flag). Pre-fix this burned the single shared
           attempt.
        2. The oversized request goes to the provider → 413.
        3. The 413 handler compresses again — the lock has been released and
           the pass now succeeds — and the retry completes.

        Pre-fix, step 3 found ``compression_attempts`` already at the cap and
        returned ``compression_exhausted`` → gateway session wipe. The defer
        refund keeps the budget intact for the provider-proven retry.
        """
        agent.max_compression_attempts = 1
        # Compressor stub: pressure only on the fully-assembled request
        # (pre-API site); the turn-context preflight stands down via the
        # cheap-gate (small message count) and low turn-context estimate.
        agent.context_compressor = SimpleNamespace(
            protect_first_n=3,
            protect_last_n=20,
            threshold_tokens=100_000,
            context_length=1_000_000,
            last_prompt_tokens=0,
            should_compress=lambda t: t >= 100_000,
            should_defer_preflight_to_real_usage=lambda _t: False,
            get_active_compression_failure_cooldown=lambda: None,
        )

        agent.client.chat.completions.create.side_effect = [
            _make_413_error(),
            _mock_response(content="Recovered after lock release"),
        ]

        compress_calls = []

        def _lock_then_success(messages, _system_message, **_kwargs):
            compress_calls.append(len(messages))
            if len(compress_calls) == 1:
                # Lock loser: no-op + #69870 signal.
                agent._compression_skipped_due_to_lock = LOCK_HOLDER
                return messages, "You are helpful."
            # Lock released: real compaction (entry clears the signal).
            agent._compression_skipped_due_to_lock = None
            return (
                [{"role": "user", "content": "hello"}],
                "You are helpful.",
            )

        with (
            patch(
                "agent.turn_context.estimate_request_tokens_rough",
                return_value=10,
            ),
            patch(
                "agent.model_metadata.estimate_request_tokens_rough",
                return_value=500_000,
            ),
            patch(
                "agent.model_metadata.estimate_messages_tokens_rough",
                return_value=500_000,
            ),
            patch.object(agent, "_compress_context", side_effect=_lock_then_success),
            patch.object(agent, "_persist_session"),
            patch.object(agent, "_save_trajectory"),
            patch.object(agent, "_cleanup_task_resources"),
        ):
            result = agent.run_conversation("hello", conversation_history=list(_PREFILL))

        # Pass 1: pre-API (lock defer, refunded). Pass 2: 413 handler
        # (succeeds within the cap because the defer did not count).
        assert len(compress_calls) == 2
        assert result.get("completed") is True
        assert result["final_response"] == "Recovered after lock release"
        assert not result.get("compression_exhausted")
        assert not result.get("compression_deferred")


def _run_pre_api_lock_defer(agent, pressure_tokens):
    messages = list(_PREFILL)
    compressor = SimpleNamespace(
        context_length=262_144,
        max_tokens=32_000,
        threshold_tokens=200_000,
        should_compress=lambda _tokens: True,
        get_active_compression_failure_cooldown=lambda: None,
    )
    agent.context_compressor = compressor
    agent.compression_enabled = True
    agent._compression_feasibility_checked = True
    agent._compression_skipped_due_to_lock = None
    agent._compress_context = _lock_skipping_compress(agent)
    agent._persist_session = MagicMock()
    verdict = PreflightGateVerdict(
        action="fallthrough", pending_moa_prepared_request=None, messages=messages,
        active_system_prompt="You are helpful.", conversation_history=None, api_call_count=1,
        compression_attempts=0, final_response=None, failed=False, _turn_exit_reason=None,
        _compression_timeout_exhausted=False, _preflight_compression_blocked=False,
        _provider_overflow_recovery_pending=False, _last_preflight_pressure=None,
    )
    return run_preflight_compression(
        agent, verdict, compressor=compressor, request_pressure_tokens=pressure_tokens,
        provider_overflow_preflight=False, defer_preflight=lambda _tokens: False,
        moa_prepared_request=None, system_message="You are helpful.", user_message="hello",
        max_compression_attempts=3, effective_task_id=None,
    )


class TestPreApiLockDeferRespectsOutputReservation:
    def test_oversized_request_is_deferred_before_provider_call(self, agent):
        # 257,249 prompt tokens fit the raw 262,144 window, but not after reserving
        # 32,000 output tokens. While the hygiene summary owns the lock, don't send it.
        verdict = _run_pre_api_lock_defer(agent, 257_249)

        assert verdict.action == "return"
        assert verdict.result["compression_deferred"] is True
        assert verdict.result["failed"] is False
        assert verdict.api_call_count == 0
        agent._persist_session.assert_called_once()

    def test_request_that_fits_prompt_and_output_still_proceeds(self, agent):
        verdict = _run_pre_api_lock_defer(agent, 220_000)

        assert verdict.action == "fallthrough"
        assert verdict.result is None
