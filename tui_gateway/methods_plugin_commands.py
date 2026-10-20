"""Late-bound plugin command lookup for the shared gateway RPC methods."""

import logging

logger = logging.getLogger(__name__)


def get_plugin_command_entry(name: str):
    try:
        from hermes_cli.plugins import get_plugin_command_entry as lookup
        return lookup(name)
    except Exception:
        logger.exception("plugin command lookup failed for /%s", name)
        return None


def slash_exec_plugin_response(rid, entry, arg, session, ok, run_plugin_command):
    try:
        output = run_plugin_command(entry["handler"], arg, session) or "(no output)"
        response = {"type": "plugin", "output": output} if entry.get("output_mode") == "transcript" else {"output": output}
        return ok(rid, response)
    except Exception as exc:
        logger.exception("plugin slash command failed")
        return ok(rid, {"output": f"Plugin command error: {exc}"})
