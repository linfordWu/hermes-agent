"""Contracts for append-only sidecar log size bounds."""

from pathlib import Path

import hermes_logging


def test_caps_sidecar_in_place_at_a_line_boundary_with_live_append_handle(tmp_path, monkeypatch):
    import hermes_logging_sidecars as sidecars

    monkeypatch.setattr(sidecars, "_SIDECAR_LOG_MAX_BYTES", 512)
    monkeypatch.setattr(sidecars, "_MARKER_RESERVE_BYTES", 96)
    path = tmp_path / "gateway-stdio.log"
    path.write_bytes(b"".join(f"line {index:03d}\n".encode() for index in range(100)))
    original_inode = path.stat().st_ino

    with path.open("ab", buffering=0) as live_writer:
        dropped = sidecars._cap_file(path)
        live_writer.write(b"written by the existing append handle\n")

    content = path.read_bytes()
    lines = content.splitlines()
    assert dropped is not None and dropped > 0
    assert len(content) <= sidecars._SIDECAR_LOG_MAX_BYTES
    assert path.stat().st_ino == original_inode
    assert lines[0].startswith(b"[Hermes log trimmed in place; discarded ")
    assert lines[-1] == b"written by the existing append handle"
    assert all(line.startswith((b"[Hermes", b"line ", b"written")) for line in lines)


def test_setup_logging_caps_profile_and_root_sidecars(tmp_path, monkeypatch):
    import hermes_logging_sidecars as sidecars

    monkeypatch.setattr(sidecars, "_SIDECAR_LOG_MAX_BYTES", 256)
    monkeypatch.setattr(sidecars, "_MARKER_RESERVE_BYTES", 96)
    root = tmp_path / "home"
    home = root / "profiles" / "work"
    profile_logs = home / "logs"
    root_logs = root / "logs"
    profile_logs.mkdir(parents=True)
    root_logs.mkdir(parents=True)
    profile_names = ("gateway-stdio.log", "mcp-stderr.log")
    root_names = tuple(name for name in sidecars._SIDECAR_LOG_NAMES if name not in profile_names)
    for directory, names in ((profile_logs, profile_names), (root_logs, root_names)):
        for name in names:
            (directory / name).write_bytes(b"old line\n" * 100)

    assert hermes_logging.setup_logging(hermes_home=home) == profile_logs

    for directory, names in ((profile_logs, profile_names), (root_logs, root_names)):
        for name in names:
            content = (directory / name).read_bytes()
            assert len(content) <= sidecars._SIDECAR_LOG_MAX_BYTES
            assert content.startswith(b"[Hermes log trimmed in place; discarded ")


def test_sidecar_cap_skips_missing_and_small_files(tmp_path, monkeypatch):
    import hermes_logging_sidecars as sidecars

    monkeypatch.setattr(sidecars, "_SIDECAR_LOG_MAX_BYTES", 256)
    small = tmp_path / "update.log"
    small.write_bytes(b"leave this file alone\n")
    original = small.read_bytes()

    assert sidecars._cap_file(tmp_path / "missing.log") is None
    assert sidecars._cap_file(small) is None
    assert small.read_bytes() == original


def test_setup_logging_bounds_a_sidecar_without_importing_the_capper(tmp_path):
    home = tmp_path / "home"
    logs = home / "logs"
    logs.mkdir(parents=True)
    path = logs / "gateway-stdio.log"
    path.write_bytes(b"old log line\n" * 750_000)

    hermes_logging.setup_logging(hermes_home=home)

    content = path.read_bytes()
    assert len(content) <= 8 * 1024 * 1024
    assert content.startswith(b"[Hermes log trimmed in place; discarded ")
