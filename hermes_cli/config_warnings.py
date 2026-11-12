"""Human-readable startup warnings from Hermes configuration loading."""

import sys
from typing import Any, Optional

from hermes_cli.stderr_color import stderr_color_enabled, stderr_sgr


def print_config_warnings(config: Optional[dict[str, Any]] = None) -> None:
    """Print config structure warnings to stderr at startup; nothing if healthy."""
    from hermes_cli.config import validate_config_structure

    try:
        issues = validate_config_structure(config)
    except Exception:  # health: allow BLE001 -- malformed optional config must not block startup.
        issues = []
    if not issues:
        return

    color_enabled = stderr_color_enabled()
    lines = [stderr_sgr("\033[33m", "⚠ Config issues detected in config.yaml:", color_enabled)]
    for issue in issues:
        marker = stderr_sgr(
            "\033[31m" if issue.severity == "error" else "\033[33m",
            "✗" if issue.severity == "error" else "⚠",
            color_enabled,
        )
        lines.append(f"  {marker} {issue.message}")
    lines.append(stderr_sgr("\033[2m", "  Run 'hermes doctor' for fix suggestions.", color_enabled))
    sys.stderr.write("\n".join(lines) + "\n\n")


def warn_deprecated_cwd_env_vars() -> None:
    """Warn when deprecated working-directory keys exist in the Hermes .env file."""
    from hermes_cli.config import load_env

    try:
        env_map = load_env()
    except Exception:  # health: allow BLE001 -- warning-only .env read failures stay silent.
        return

    color_enabled = stderr_color_enabled()
    warning_marker = stderr_sgr("\033[33m", "⚠", color_enabled)
    lines = []
    for name in ("MESSAGING_CWD", "TERMINAL_CWD"):
        val = str(env_map.get(name) or "").strip()
        if val:
            lines.append(f"  {warning_marker} {name}={val} found in .env — this is deprecated.")
    if lines:
        from hermes_constants import display_hermes_home

        hint_path = display_hermes_home()
        lines.insert(0, stderr_sgr("\033[33m", "⚠ Deprecated .env settings detected:", color_enabled))
        lines.append(
            stderr_sgr(
                "\033[2m",
                "  Move to config.yaml instead:  terminal:\\n    cwd: /your/project/path",
                color_enabled,
            )
        )
        lines.append(
            stderr_sgr(
                "\033[2m",
                f"  Then remove the old entries from {hint_path}/.env",
                color_enabled,
            )
        )
        sys.stderr.write("\n".join(lines) + "\n\n")
