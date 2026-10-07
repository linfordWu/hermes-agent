"""Explicit API request providers must not inherit the default provider's wire options."""

import pytest

from gateway.platforms.api_server import (
    _apply_runtime_agent_overrides,
    _resolve_request_runtime_agent_kwargs,
)


@pytest.mark.parametrize(
    "provider_request_overrides",
    [{}, {"extra_body": {"temperature": 0.2}}],
)
def test_request_provider_replaces_default_request_overrides(monkeypatch, provider_request_overrides):
    target_runtime = {
        "api_key": "target-key",
        "base_url": "https://target.example/v1",
        "provider": "openai-codex",
        "api_mode": "codex_responses",
        "command": None,
        "args": [],
        "credential_pool": None,
        "request_overrides": provider_request_overrides,
    }
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        lambda **_kwargs: target_runtime,
    )

    resolved = _resolve_request_runtime_agent_kwargs("openai-codex", target_model="gpt-6.1-sol")
    runtime_kwargs = {
        "provider": "custom-default",
        "request_overrides": {"extra_body": {"max_tokens": 8192, "include_reasoning": True}},
    }

    _apply_runtime_agent_overrides(runtime_kwargs, resolved)

    assert runtime_kwargs["provider"] == "openai-codex"
    assert runtime_kwargs["request_overrides"] == provider_request_overrides
