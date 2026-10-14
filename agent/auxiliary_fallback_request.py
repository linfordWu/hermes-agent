"""Request construction shared by the auxiliary provider fallback ladder."""

from typing import Any, Optional


def _extra_body_for_fallback(
    destination: Any, *, primary_provider: Optional[str], primary_base_url: Optional[str],
    effective_extra_body: dict, fallback_entry: dict, normalize_provider,
) -> dict[str, Any]:
    """Keep request passthrough fields only when a fallback stays on the same route.

    ``extra_body`` is endpoint-specific. Carrying a local OpenAI-compatible endpoint's vendor
    fields to another provider can make an otherwise healthy fallback fail validation (for
    example, Anthropic rejects Qwen's ``chat_template_kwargs``). A fallback entry can declare
    its own body for its destination.
    """
    primary_name = normalize_provider(primary_provider)
    fallback_name = normalize_provider(destination.provider)
    primary_url = str(primary_base_url or "").strip().rstrip("/")
    fallback_url = str(destination.base_url or "").strip().rstrip("/")
    same_route = primary_name == fallback_name and primary_url == fallback_url
    body = dict(effective_extra_body) if same_route and isinstance(effective_extra_body, dict) else {}
    entry_body = fallback_entry.get("extra_body")
    if isinstance(entry_body, dict):
        body.update(entry_body)
    return body


def fallback_request_kwargs(
    destination: Any, *, task: Optional[str], messages: list,
    tools: Optional[list], temperature: Optional[float], max_tokens: Optional[int],
    effective_timeout: float, effective_extra_body: dict, reasoning_config: Optional[dict],
    fallback_entry: dict, task_config: dict, apply_fast_lane: bool,
    primary_provider: Optional[str] = None, primary_base_url: Optional[str] = None,
) -> dict[str, Any]:
    """Build request kwargs for one fallback destination.

    Import the auxiliary-client helpers lazily to keep this module independent at import time;
    ``auxiliary_client`` imports this function while initializing the recovery ladder.
    """
    from agent.auxiliary_client import (
        _build_call_kwargs,
        _compression_fast_lane_controls,
        _normalize_aux_provider,
        _replan_synchronous_cache_sections,
    )

    fallback_max_tokens = max_tokens
    fallback_extra_body = _extra_body_for_fallback(
        destination,
        primary_provider=primary_provider,
        primary_base_url=primary_base_url,
        effective_extra_body=effective_extra_body,
        fallback_entry=fallback_entry,
        normalize_provider=_normalize_aux_provider,
    )
    if apply_fast_lane:
        fallback_max_tokens, fallback_extra_body = _compression_fast_lane_controls(
            task, actual_provider=destination.provider, actual_model=destination.model,
            requested_provider=fallback_entry.get("provider"),
            requested_model=fallback_entry.get("model"), route_config=fallback_entry,
            leak_guard_config=task_config, max_tokens=max_tokens, extra_body=fallback_extra_body,
        )
    fallback_messages, fallback_tools = _replan_synchronous_cache_sections(
        messages, tools, destination=destination,
    )
    return _build_call_kwargs(
        destination.provider, destination.model, fallback_messages,
        temperature=temperature, max_tokens=fallback_max_tokens, tools=fallback_tools,
        timeout=effective_timeout, extra_body=fallback_extra_body,
        reasoning_config=reasoning_config, base_url=destination.base_url, task=task,
    )
