"""Credential-resolution failures may use a configured route's fallback chain (#146645)."""

from unittest.mock import patch

import pytest

from hermes_cli.auth_constants import AuthError


def _raise_auth(message):
    try:
        raise AuthError(message, provider="codex", code="usage_limit_reached")
    except AuthError as cause:
        raise ValueError(message) from cause


def test_route_tries_fallback_entries_in_order_and_keeps_the_remaining_chain():
    from tools.delegate_tool_routes import _resolve_route

    entries = [
        {"provider": "openai-codex", "model": "primary-backup"},
        {"provider": "xai-oauth", "model": "healthy", "reasoning_effort": "high"},
        {"provider": "openrouter", "model": "last"},
    ]
    seen = []

    def resolve(route, _parent):
        seen.append(route)
        if route["provider"] != "xai-oauth":
            _raise_auth(f"{route['provider']} unavailable")
        return {"provider": route["provider"], "model": route["model"], "api_key": "key"}

    with patch("tools.delegate_tool._resolve_delegation_credentials", side_effect=resolve):
        resolved = _resolve_route({"provider": "openai-codex", "model": "primary", "fallback_providers": entries},
                                  object(), "default")

    assert [route["provider"] for route in seen] == ["openai-codex", "openai-codex", "xai-oauth"]
    assert resolved.creds["model"] == "healthy"
    assert resolved.reasoning_effort == "high"
    assert resolved.routing_cfg["fallback_providers"] == entries[2:]


def test_healthy_primary_does_not_resolve_or_consume_fallbacks():
    from tools.delegate_tool_routes import _resolve_route

    route = {"provider": "openrouter", "model": "primary",
             "fallback_providers": [{"provider": "xai-oauth", "model": "backup"}]}
    parent = object()
    with patch("tools.delegate_tool._resolve_delegation_credentials", return_value={"api_key": "primary-key"}) as resolve:
        resolved = _resolve_route(route, parent, "default")

    resolve.assert_called_once_with(route, parent)
    assert resolved.creds == {"api_key": "primary-key"}
    assert resolved.routing_cfg is route


def test_non_auth_primary_error_does_not_try_fallbacks():
    from tools.delegate_tool_routes import _resolve_route

    route = {"provider": "openrouter", "fallback_providers": [{"provider": "xai-oauth", "model": "backup"}]}
    error = ValueError("invalid pinned command")
    with patch("tools.delegate_tool._resolve_delegation_credentials", side_effect=error) as resolve:
        with pytest.raises(ValueError, match="invalid pinned command") as raised:
            _resolve_route(route, object(), "default")

    assert raised.value is error
    resolve.assert_called_once()


def test_when_all_fallback_credentials_refuse_the_primary_error_is_preserved():
    from tools.delegate_tool_routes import _resolve_route

    route = {"provider": "openai-codex", "model": "primary", "fallback_providers": [
        {"provider": "xai-oauth", "model": "backup-a"},
        {"provider": "openrouter", "model": "backup-b"},
    ]}
    primary_errors = []

    def resolve(candidate, _parent):
        if candidate is route:
            try:
                raise AuthError("quota exhausted", provider="codex", code="usage_limit_reached")
            except AuthError as cause:
                error = ValueError("primary quota exhausted")
                primary_errors.append(error)
                raise error from cause
        _raise_auth(f"{candidate['provider']} unavailable")

    with patch("tools.delegate_tool._resolve_delegation_credentials", side_effect=resolve):
        with pytest.raises(ValueError, match="primary quota exhausted") as raised:
            _resolve_route(route, object(), "default")

    assert raised.value is primary_errors[0]
