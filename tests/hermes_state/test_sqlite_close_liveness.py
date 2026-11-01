"""A slow SQLite close must not convoy the process-wide tracking registry."""

import sqlite3
import threading

from hermes_cli.sqlite_safe_read import (
    connect_tracked,
    has_live_connection,
    read_header_bytes_preopen,
)


def test_slow_close_keeps_probe_guard_without_blocking_other_connections(tmp_path):
    closing = threading.Event()
    release = threading.Event()
    inspected = threading.Event()
    observations = []
    errors = []

    class SlowClose(sqlite3.Connection):
        def close(self):
            closing.set()
            if not release.wait(15):
                raise RuntimeError("test did not release the close")
            super().close()

    path = tmp_path / "closing.db"
    conn = connect_tracked(path, factory=SlowClose, check_same_thread=False)
    conn.execute("CREATE TABLE evidence(value)")

    def inspect():
        try:
            observations.append(has_live_connection(path))
            observations.append(read_header_bytes_preopen(path, length=16))
            other = connect_tracked(tmp_path / "other.db")
            try:
                observations.append(other.execute("SELECT 1").fetchone()[0])
            finally:
                other.close()
        except Exception as exc:  # capture failures from the worker for the test thread
            errors.append(exc)
        finally:
            inspected.set()

    closer = threading.Thread(target=conn.close, daemon=True)
    reader = threading.Thread(target=inspect, daemon=True)
    try:
        closer.start()
        assert closing.wait(5)
        reader.start()
        assert inspected.wait(5), (
            "one blocked close stalled all database tracking/opens"
        )
        assert not errors
        assert observations == [True, None, 1]
    finally:
        release.set()
        closer.join(10)
        if reader.ident is not None:
            reader.join(10)
    assert not closer.is_alive() and not reader.is_alive()
    assert not has_live_connection(path)
