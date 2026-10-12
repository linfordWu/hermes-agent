"""Config-backed context-window overrides for model/provider routes."""

import contextlib
from typing import Optional


def _custom_endpoint_override_candidates(
    provider: str, base_url: str, custom_providers: list | None,
) -> list[str]:
    """Provider override keys for a URL-routed custom endpoint, in specificity order."""
    provider_key = (provider or "").strip()
    if not provider_key.lower().startswith("custom:"):
        return []
    route_url = (base_url or provider_key[len("custom:"):]).strip()
    if not route_url:
        return []
    from hermes_cli.config_providers import get_compatible_custom_providers
    from hermes_cli.route_identity import normalize_route_base_url

    entries = custom_providers if isinstance(custom_providers, list) else get_compatible_custom_providers()
    target_url = normalize_route_base_url(route_url)
    matches = [
        entry for entry in entries
        if isinstance(entry, dict)
        and normalize_route_base_url(entry.get("base_url")) == target_url
    ]

    # The URL identifies a route, not necessarily a unique provider: don't borrow a
    # provider-scoped override when several configured names share the same endpoint.
    names = {str(entry.get("name") or "").strip() for entry in matches}
    names.discard("")
    candidates = [next(iter(names))] if len(names) == 1 else []
    catalog_providers = {str(entry.get("catalog_provider") or "").strip() for entry in matches}
    catalog_providers.discard("")
    if len(catalog_providers) == 1:
        candidates.extend(catalog_providers)
    return list(dict.fromkeys(candidates))


def _config_override_context_length(
    model: str, base_url: str, provider: str, custom_providers: list | None,
) -> Optional[int]:
    """Resolve explicit model/context overrides before probes or catalog fallback."""
    if provider and model:
        with contextlib.suppress(Exception):  # malformed or unreadable config falls through
            from agent.models_dev import _override_context_window

            mo_ctx = _override_context_window(provider, model)
            if mo_ctx is not None and mo_ctx > 0:
                return mo_ctx
        provider_candidates = []
        with contextlib.suppress(Exception):  # a failed route lookup must not mask other sources
            provider_candidates = _custom_endpoint_override_candidates(
                provider, base_url, custom_providers,
            )
        for provider_candidate in provider_candidates:
            with contextlib.suppress(Exception):
                mo_ctx = _override_context_window(provider_candidate, model)
                if mo_ctx is not None and mo_ctx > 0:
                    return mo_ctx
    if base_url and model:
        with contextlib.suppress(Exception):  # fall through to probing
            from hermes_cli.config import get_custom_provider_context_length

            cp_ctx = get_custom_provider_context_length(
                model=model, base_url=base_url, custom_providers=custom_providers,
            )
            if cp_ctx:
                return cp_ctx
    return None
