"""Deferred context-engine notifications for an outer compression transaction."""

from typing import Any, Callable


_PENDING_CONTEXT_ENGINE_NOTIFICATION = "_pending_context_engine_compression_notification"


def queue_context_engine_compression_notification(agent: Any, notify: Callable[[], bool]) -> None:
    """Stage one notification; sessions without an attached agent have no hook to stage."""
    if agent is None:
        return
    if callable(getattr(agent, _PENDING_CONTEXT_ENGINE_NOTIFICATION, None)):
        raise RuntimeError("a compression notification is already pending")
    setattr(agent, _PENDING_CONTEXT_ENGINE_NOTIFICATION, notify)


def finalize_context_engine_compression_notification(agent: Any, *, committed: bool) -> bool:
    """Emit or discard a deferred notification; missing agents and repeated calls are no-ops."""
    if agent is None:
        return False
    pending = getattr(agent, _PENDING_CONTEXT_ENGINE_NOTIFICATION, None)
    setattr(agent, _PENDING_CONTEXT_ENGINE_NOTIFICATION, None)
    if not committed or not callable(pending):
        return False
    return bool(pending())
