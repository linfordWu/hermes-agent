"""Decide when building the CLI parser requires plugin command discovery."""

from __future__ import annotations

import sys

from hermes_cli._parser import command_argv


# Keep in sync with the add_parser calls in main._build_cli_parser. An extra
# entry would let a plugin command silently fail to parse.
_BUILTIN_SUBCOMMANDS = frozenset(
    {
        "acp", "approvals", "auth", "backup", "bundles", "checkpoints", "codex-runtime", "completion",
        "computer-use", "connectors",
        "config", "console", "cron", "curator", "dashboard", "serve", "debug", "doctor",
        "dump", "egress", "fallback", "gateway", "hooks", "import", "insights",
        "gui", "desktop", "kanban", "login", "logout", "logs", "lsp", "mcp", "memory", "migrate", "moa",
        "journey", "memory-graph", "learning",
        "model", "monitoring", "pairing", "pause", "peer", "pets", "plugins", "portal", "profile",
        "project", "proxy",
        "prompt-size",
        "resume",
        "send", "sessions", "setup",
        "skin", "skills", "slack", "status", "tools", "uninstall", "update",
        "usage", "vault",
        "webhook", "whatsapp", "whatsapp-cloud", "worktree", "chat", "secrets", "security",
        "browser",
        "verify",
        "help",
    }
)


def _first_positional_argv() -> str | None:
    """First non-flag, non-flag-value token in ``sys.argv[1:]``."""
    args = command_argv(sys.argv[1:])
    return args[0] if args else None


def _plugin_cli_discovery_needed() -> bool:
    """Whether invocation needs plugin commands in the argparse tree.

    Ordinary built-ins skip eager plugin discovery (~500-650ms). Unknown first
    tokens may be plugin commands or chat prompts, so they need discovery too.
    Top-level help and shell completion must enumerate the complete command tree.
    """
    first = _first_positional_argv()  # None = bare ``hermes`` → chat
    if _plugin_cli_discovery_all_commands_needed():
        return True
    return first is not None and first not in _BUILTIN_SUBCOMMANDS


def _plugin_cli_discovery_all_commands_needed() -> bool:
    """Whether introspection needs deferred platform commands materialized too."""
    first = _first_positional_argv()
    return first == "completion" or (
        first is None and any(arg in {"-h", "--help"} for arg in sys.argv[1:])
    )
