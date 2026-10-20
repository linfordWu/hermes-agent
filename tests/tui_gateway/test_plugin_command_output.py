"""Output policy for plugin slash commands in the shared TUI gateway."""

import pytest

from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
from tui_gateway import server


def test_plugin_command_output_mode_defaults_to_notice_and_accepts_transcript():
    ctx = PluginContext(PluginManifest(name="output-test", source="user"), PluginManager())

    ctx.register_command("default", lambda _arg: "default")
    ctx.register_command("transcript", lambda _arg: "long", output_mode="transcript")
    ctx.register_command("invalid", lambda _arg: "safe", output_mode="other")

    commands = ctx._manager._plugin_commands
    assert commands["default"]["output_mode"] == "notice"
    assert commands["transcript"]["output_mode"] == "transcript"
    assert commands["invalid"]["output_mode"] == "notice"


@pytest.mark.parametrize(
    ("output_mode", "expected"),
    [
        ("transcript", {"type": "plugin", "output": "\n".join(f"row {i}" for i in range(20))}),
        ("notice", {"output": "\n".join(f"row {i}" for i in range(20))}),
    ],
)
def test_slash_exec_returns_dispatch_only_for_transcript_output(monkeypatch, output_mode, expected):
    output = "\n".join(f"row {i}" for i in range(20))
    entry = {"handler": lambda _arg: output, "output_mode": output_mode}
    monkeypatch.setattr("hermes_cli.plugins.get_plugin_command_entry", lambda _name: entry)
    monkeypatch.setattr(server, "_sessions", {"sid": {"session_key": "session-key", "cwd": ""}})

    response = server._methods["slash.exec"]("d", {"command": "manylines", "session_id": "sid"})

    assert response["result"] == expected
