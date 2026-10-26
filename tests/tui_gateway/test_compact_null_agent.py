"""Compression cleanup must not mask an error on a restored session without a live agent."""

import threading
from types import SimpleNamespace


def test_stale_compress_snapshot_uses_callers_live_agent(monkeypatch):
    from tui_gateway import server

    monkeypatch.setattr(server, "_get_usage", lambda _agent: {})
    monkeypatch.setattr(server, "_set_session_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_clear_session_context", lambda _tokens: None)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(6)]
    session = {
        "agent": None,
        "history_lock": threading.Lock(),
        "history": list(history),
        "history_version": 1,
        "session_key": "restored-session",
    }
    live_agent = SimpleNamespace()

    def _compress(_agent, _messages, _request, **_kwargs):
        session["history_version"] = 2  # simulate an external edit during compression
        return SimpleNamespace(status="compressed", after_messages=[], removed=4)

    monkeypatch.setattr("agent.conversation_compression_manual.compress_now", _compress)

    assert server._compress_session_history(session, agent=live_agent) == (0, {})


def test_compress_mirror_without_agent_returns_refusal():
    from tui_gateway import server

    assert server._SLASH_MIRRORS["compress"]("sid", {}, None, "") == "No active agent -- send a message first."
