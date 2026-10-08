"""Provider-derived environment variable metadata for CLI configuration."""

from pathlib import Path
import logging
import sys

logger = logging.getLogger(__name__)


def inject_profile_env_vars(optional_env_vars: dict[str, dict]) -> None:
    """Expose API-key provider variables without loading providers in PM's minimal runtime."""
    if (Path(sys.prefix) / "pm-runtime.json").is_file():
        return
    try:
        from providers import list_providers

        for provider in list_providers():
            if provider.auth_type != "api_key":
                continue
            for variable in provider.env_vars:
                if variable in optional_env_vars:
                    continue
                is_key = not variable.endswith(("_BASE_URL", "_URL"))
                label = provider.display_name or provider.name
                optional_env_vars[variable] = {
                    "description": f"{label} {'API key' if is_key else 'base URL override'}",
                    "prompt": f"{label} {'API key' if is_key else 'base URL (leave empty for default)'}",
                    "url": provider.signup_url or None,
                    "password": is_key,
                    "category": "provider",
                    "advanced": True,
                }
    except Exception:
        logger.debug("Provider environment-variable metadata discovery failed", exc_info=True)
