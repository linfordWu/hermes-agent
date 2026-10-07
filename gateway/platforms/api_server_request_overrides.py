"""Provider runtime fields used by explicit API request overrides."""

from typing import Any, Dict, Optional


_RUNTIME_AGENT_OVERRIDE_KEYS = (
    "api_key", "base_url", "provider", "api_mode", "command", "args", "credential_pool",
    "request_overrides")


def _apply_runtime_agent_overrides(
    runtime_kwargs: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge resolved provider/runtime fields into ``runtime_kwargs`` in place."""
    if not isinstance(overrides, dict):
        return runtime_kwargs
    for key in _RUNTIME_AGENT_OVERRIDE_KEYS:
        value = overrides.get(key)
        if value is None:
            continue
        runtime_kwargs[key] = list(value) if key == "args" and isinstance(value, (list, tuple)) else value
    return runtime_kwargs


def _resolve_request_runtime_agent_kwargs(
    provider: str, target_model: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve an explicit request provider without mutating config.yaml."""
    from hermes_cli.runtime_provider import resolve_runtime_provider, format_runtime_provider_error

    try:
        runtime = resolve_runtime_provider(requested=provider, target_model=target_model)
    except Exception as exc:
        raise RuntimeError(format_runtime_provider_error(exc)) from exc

    return {
        **{key: runtime.get(key) for key in ("api_key", "base_url", "provider", "api_mode", "command")},
        "args": list(runtime.get("args") or []),
        "credential_pool": runtime.get("credential_pool"),
        "request_overrides": dict(runtime.get("request_overrides") or {}),
    }
