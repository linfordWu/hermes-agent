"""`kanban edit --body-file` replaces task bodies from a file or stdin (#137599)."""

from __future__ import annotations

import argparse
import io
from pathlib import Path

import pytest

from hermes_cli import kanban as kc
from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc

BODY = "line one\nline two with `backticks`\n--priority 99\n"


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _edit(task_id: str, *argv: str, monkeypatch=None, stdin=None) -> int:
    root = argparse.ArgumentParser(prog="hermes")
    kc.build_parser(root.add_subparsers())
    args = root.parse_args(["kanban", "edit", task_id, *argv])
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return kc._cmd_edit(args)


def _task(task_id: str):
    with kbc.connect_closing() as conn:
        return kb.get_task(conn, task_id)


def test_body_file_replaces_body_verbatim_and_keeps_other_fields(kanban_home, tmp_path, capsys):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title="keep title", body="old body", priority=7)
    body_file = tmp_path / "body.md"
    body_file.write_text(BODY, encoding="utf-8-sig")

    assert _edit(task_id, "--body-file", str(body_file)) == 0
    capsys.readouterr()
    task = _task(task_id)
    assert (task.title, task.body, task.priority) == ("keep title", BODY, 7)


def test_body_file_dash_reads_stdin(kanban_home, monkeypatch, capsys):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title="stdin", body="old")

    assert _edit(task_id, "--body-file", "-", monkeypatch=monkeypatch, stdin=BODY) == 0
    capsys.readouterr()
    assert _task(task_id).body == BODY


def test_body_and_body_file_are_mutually_exclusive(kanban_home, tmp_path, capsys):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title="conflict", body="unchanged")
    body_file = tmp_path / "body.md"
    body_file.write_text(BODY, encoding="utf-8")

    assert _edit(task_id, "--body", "inline", "--body-file", str(body_file)) == 2
    assert _task(task_id).body == "unchanged"


def test_unreadable_body_file_refuses_edit(kanban_home, tmp_path, capsys):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title="missing", body="unchanged")

    assert _edit(task_id, "--body-file", str(tmp_path / "missing.md")) == 2
    assert _task(task_id).body == "unchanged"


def test_invalid_utf8_body_file_refuses_edit(kanban_home, tmp_path):
    with kbc.connect_closing() as conn:
        task_id = kb.create_task(conn, title="invalid", body="unchanged")
    body_file = tmp_path / "invalid.md"
    body_file.write_bytes(b"\xff")

    assert _edit(task_id, "--body-file", str(body_file)) == 2
    assert _task(task_id).body == "unchanged"
