"""ANSI color helpers for output sent specifically to standard error."""

import os
import sys


def stderr_color_enabled() -> bool:
    """Return whether stderr supports ANSI color, honoring standard opt-outs."""
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(sys.stderr.isatty())
    except (AttributeError, OSError):
        return False


def stderr_sgr(code: str, text: str, enabled: bool) -> str:
    """Wrap text in an SGR sequence only when stderr color is enabled."""
    return f"{code}{text}\033[0m" if enabled else text
