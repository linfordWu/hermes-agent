"""Regression tests for config-backed context-window override resolution."""

from unittest.mock import patch

from agent.model_metadata import get_model_context_length
from agent.model_metadata_overrides import _config_override_context_length


def test_custom_endpoint_context_override_uses_matching_provider_name():
    """A custom URL route resolves model_overrides through its configured name (#102425)."""
    base_url = "http://127.0.0.1:4444/providers/opencode-go"
    custom_providers = [{
        "name": "proxy-ocgo",
        "base_url": f"{base_url}/",
        "catalog_provider": "opencode-go",
    }]
    overrides = {
        "proxy-ocgo": {"space-bunny": {"context_window": 1_048_576}},
    }

    with patch("agent.models_dev._load_model_overrides", return_value=overrides):
        assert get_model_context_length(
            "space-bunny", base_url=base_url, provider=f"custom:{base_url}",
            custom_providers=custom_providers,
        ) == 1_048_576

        # The same override must not leak to a different custom endpoint.
        assert _config_override_context_length(
            "space-bunny", "http://127.0.0.1:4444/other", f"custom:{base_url}", custom_providers,
        ) is None
