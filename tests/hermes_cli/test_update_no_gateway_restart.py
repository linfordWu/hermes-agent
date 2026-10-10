"""The PM completion child honors --no-gateway-restart without skipping preparation (#93649)."""
import argparse
import json
import shutil
import sys

from hermes_cli import update_completion
from hermes_cli._old_updater import _historical_context
from hermes_cli.update_finish import finish_update
from hermes_cli.subcommands.update import build_update_parser
from tests.hermes_cli.test_update_completion_process import transition


def test_restart_deferral_crosses_real_completion_process(transition):
    root, _git, _old, _new, request = transition
    parser = argparse.ArgumentParser()
    build_update_parser(parser.add_subparsers(), cmd_update=lambda args: None)
    request["no_gateway_restart"] = parser.parse_args(["update", "--no-gateway-restart"]).no_gateway_restart
    shutil.copy2(update_completion.__file__, root / "hermes_cli/update_completion.py")
    receipt = root / "hermes_cli/update_receipt.py"
    with receipt.open("a", encoding="utf-8") as stream:
        stream.write("\nfrom hermes_cli.probe import event\ndef record_skip(*args): event('deferred')\n")
    marker = root / "fleet_restart_pending"
    marker.write_text("pending", encoding="utf-8")

    result = update_completion.run_completion(request)

    assert result["exit_code"] == 0
    assert result["receipt"]["outcome"] == "success"
    assert result["windows_resume"]["resume_needed"] is False
    events = [json.loads(line)["name"] for line in (root / "events.jsonl").read_text().splitlines()]
    assert {"prepare", "build", "maintenance", "deferred", "emergency_resume"} <= set(events)
    assert "restart" not in events and "verify" not in events
    assert marker.read_text() == "pending"


def test_historical_takeover_captures_restart_deferral_from_argv(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["hermes", "update", "--no-gateway-restart"])

    request, _resumes, _receipt_slot = _historical_context()

    assert request["no_gateway_restart"] is True


def test_historical_completion_defers_gateway_restart(tmp_path, monkeypatch):
    from hermes_cli import source_stamp, update_cmd, update_receipt, venv_sync

    events = []
    monkeypatch.setattr(update_cmd, "_run_post_update_maintenance", lambda **kwargs: True)
    monkeypatch.setattr(source_stamp, "write_source_stamp", lambda root: events.append("stamp"))
    monkeypatch.setattr(venv_sync, "clear_completion", lambda root: events.append("clear"))
    monkeypatch.setattr(update_cmd, "_restart_gateway_fleet_after_update", lambda *args: events.append("restart"))
    monkeypatch.setattr(update_receipt, "record_skip", lambda *args: events.append(("skip", *args)))
    monkeypatch.setattr(update_receipt, "record_stage", lambda *args, **kwargs: events.append(("stage", *args)))

    finish_update(
        root=tmp_path,
        assume_yes=True,
        gateway_mode=False,
        pre_update_snapshot_id=None,
        had_desktop_app_before_update=False,
        pre_update_version=None,
        plan=None,
        windows_resume=None,
        no_gateway_restart=True,
    )

    assert events == [
        ("stage", "build", "success"),
        "stamp",
        "clear",
        ("skip", "gateway_restart", "--no-gateway-restart: deferred, marker kept"),
        ("stage", "restart", "skipped"),
    ]
