"""Best-effort size bounds for append-only log files without rotating handlers."""

import os
import stat
import threading
from pathlib import Path
from typing import Iterable

_SIDECAR_LOG_MAX_BYTES = 8 * 1024 * 1024
_SIDECAR_LOG_NAMES = (
    "gateway-stdio.log",
    "bootstrap-installer.log",
    "update.log",
    "desktop-update-handoff.log",
    "mcp-stderr.log",
)
_MARKER_RESERVE_BYTES = 128
_checked_log_dirs: set[str] = set()
_checked_log_dirs_lock = threading.Lock()


def _cap_file(path: Path) -> int | None:
    """Trim a sidecar in place, retaining complete recent lines; return bytes dropped."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size <= _SIDECAR_LOG_MAX_BYTES:
        return None

    with path.open("r+b") as stream:
        size = os.fstat(stream.fileno()).st_size
        if size <= _SIDECAR_LOG_MAX_BYTES:
            return None

        start = max(0, size - (_SIDECAR_LOG_MAX_BYTES - _MARKER_RESERVE_BYTES))
        stream.seek(start)
        if start:
            stream.readline()
        recent = stream.read()
        dropped = size - len(recent)
        marker = f"[Hermes log trimmed in place; discarded {dropped} earlier bytes]\n".encode()

        while len(marker) + len(recent) > _SIDECAR_LOG_MAX_BYTES:
            excess = len(marker) + len(recent) - _SIDECAR_LOG_MAX_BYTES
            boundary = recent.find(b"\n", excess)
            recent = recent[boundary + 1:] if boundary >= 0 else b""
            dropped = size - len(recent)
            marker = f"[Hermes log trimmed in place; discarded {dropped} earlier bytes]\n".encode()

        stream.seek(0)
        stream.write(marker)
        stream.write(recent)
        stream.truncate()
    return dropped


def cap_uncapped_sidecar_logs(log_dirs: Iterable[Path]) -> list[str]:
    """Cap known append-only files once per process and log directory.

    These files have independent append writers, so rotation would leave a live writer
    attached to the renamed file. Truncation keeps the same file object and lets append
    handles continue at the new end. Failures must not prevent Hermes from starting.
    """
    messages = []
    unique_dirs = {os.path.normcase(os.path.abspath(path)) for path in log_dirs}
    for directory in sorted(unique_dirs):
        with _checked_log_dirs_lock:
            if directory in _checked_log_dirs:
                continue
            _checked_log_dirs.add(directory)
        for name in _SIDECAR_LOG_NAMES:
            path = Path(directory) / name
            try:
                _cap_file(path)
            except OSError as exc:
                messages.append(f"Could not cap sidecar log {path}: {exc}")
    return messages
