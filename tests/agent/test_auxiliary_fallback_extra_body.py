"""Provider-specific auxiliary request bodies must not leak across fallback routes."""

from agent.auxiliary_client import _FallbackDestination, _fallback_request_kwargs


def _build_kwargs(monkeypatch):
    captured = {}

    def build_call_kwargs(provider, model, messages, **kwargs):
        captured.update(provider=provider, model=model, **kwargs)
        return captured

    monkeypatch.setattr("agent.auxiliary_client._build_call_kwargs", build_call_kwargs)
    monkeypatch.setattr(
        "agent.auxiliary_client._replan_synchronous_cache_sections",
        lambda messages, tools, *, destination: (messages, tools),
    )
    return captured


def _fallback_kwargs(monkeypatch, *, primary_provider, primary_base_url, effective_extra_body, fallback_entry):
    destination = _FallbackDestination(
        "anthropic", "https://api.anthropic.com/v1", "anthropic_messages", "claude-haiku-5-5",
    )
    return _fallback_request_kwargs(
        destination,
        task="explain_command",
        messages=[{"role": "user", "content": "Explain this command"}],
        tools=None,
        temperature=None,
        max_tokens=256,
        effective_timeout=10,
        effective_extra_body=effective_extra_body,
        reasoning_config=None,
        fallback_entry=fallback_entry,
        task_config={},
        apply_fast_lane=False,
        primary_provider=primary_provider,
        primary_base_url=primary_base_url,
    )


def test_fallback_to_anthropic_drops_primary_provider_extra_body(monkeypatch):
    captured = _build_kwargs(monkeypatch)

    _fallback_kwargs(
        monkeypatch,
        primary_provider="custom:mylocal",
        primary_base_url="http://127.0.0.1:18000/v1",
        effective_extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        fallback_entry={"provider": "anthropic", "model": "claude-haiku-5-5"},
    )

    assert captured["provider"] == "anthropic"
    assert captured["extra_body"] == {}


def test_anthropic_request_builder_does_not_emit_local_vendor_fields(monkeypatch):
    monkeypatch.setattr(
        "agent.auxiliary_client._replan_synchronous_cache_sections",
        lambda messages, tools, *, destination: (messages, tools),
    )

    kwargs = _fallback_request_kwargs(
        _FallbackDestination(
            "anthropic", "https://api.anthropic.com/v1", "anthropic_messages", "claude-haiku-5-5",
        ),
        task="explain_command",
        messages=[{"role": "user", "content": "Explain this command"}],
        tools=None,
        temperature=None,
        max_tokens=256,
        effective_timeout=10,
        reasoning_config=None,
        fallback_entry={"provider": "anthropic", "model": "claude-haiku-5-5"},
        task_config={},
        apply_fast_lane=False,
        primary_provider="custom:mylocal",
        primary_base_url="http://127.0.0.1:18000/v1",
        effective_extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    assert "chat_template_kwargs" not in (kwargs.get("extra_body") or {})


def test_fallback_entry_extra_body_is_used_after_changing_provider(monkeypatch):
    captured = _build_kwargs(monkeypatch)

    _fallback_kwargs(
        monkeypatch,
        primary_provider="custom:mylocal",
        primary_base_url="http://127.0.0.1:18000/v1",
        effective_extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        fallback_entry={
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
            "extra_body": {"fallback_marker": "anthropic-specific"},
        },
    )

    assert captured["extra_body"] == {"fallback_marker": "anthropic-specific"}


def test_same_provider_fallback_keeps_task_extra_body(monkeypatch):
    captured = _build_kwargs(monkeypatch)

    destination = _FallbackDestination(
        "custom:mylocal", "http://127.0.0.1:18000/v1", "", "qwen-local",
    )
    _fallback_request_kwargs(
        destination,
        task="explain_command",
        messages=[{"role": "user", "content": "Explain this command"}],
        tools=None,
        temperature=None,
        max_tokens=256,
        effective_timeout=10,
        effective_extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        reasoning_config=None,
        fallback_entry={"provider": "custom:mylocal", "model": "qwen-local"},
        task_config={},
        apply_fast_lane=False,
        primary_provider="custom:mylocal",
        primary_base_url="http://127.0.0.1:18000/v1/",
    )

    assert captured["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
