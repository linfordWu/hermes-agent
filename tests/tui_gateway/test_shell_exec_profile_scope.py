"""Profile isolation regressions for the TUI ``shell.exec`` RPC."""

from __future__ import annotations

import contextlib
import os
import subprocess

from tools import env_passthrough
from agent import secret_scope
from tui_gateway import server


def test_shell_exec_builds_env_inside_requested_profile_scope(monkeypatch, tmp_path):
    key = "OP_SERVICE_ACCOUNT_TOKEN"
    launch_secret = "launch-profile-secret"
    profile_secret = "routed-profile-secret"
    captured = {}

    monkeypatch.setenv(key, launch_secret)
    monkeypatch.setattr(server, "_profile_home", lambda _profile: tmp_path)
    monkeypatch.setattr(env_passthrough, "_allowed_env_vars", {key})

    @contextlib.contextmanager
    def profile_scope(_session):
        token = secret_scope.set_secret_scope({key: profile_secret}, profile_home=str(tmp_path))
        try:
            yield
        finally:
            secret_scope.reset_secret_scope(token)

    monkeypatch.setattr(server, "_session_profile_runtime_scope", profile_scope)

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    token = secret_scope.set_multiplex_context(True)
    try:
        response = server.handle_request({
            "id": "profile-scope",
            "method": "shell.exec",
            "params": {"command": "true", "profile": "secondary"},
        })
    finally:
        secret_scope.reset_multiplex_context(token)

    assert response["result"]["code"] == 0
    assert captured["env"][key] == profile_secret
    assert os.environ[key] == launch_secret
