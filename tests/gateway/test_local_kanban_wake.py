"""LOCAL Kanban wake delivery uses the owning gateway's FIFO admission path (#143268)."""
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_local_kanban_wake_uses_owner_runner(monkeypatch):
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.session_local import LocalSessionAdapter
    from gateway.wake import deliver_wake

    runner = object()
    authority = SimpleNamespace(runner=runner, sessions={})
    adapter = LocalSessionAdapter(authority)
    source = SessionSource(platform=Platform.LOCAL, chat_id="local-chat", user_id="owner")
    admitted = []

    async def admit_route_wake(actual_runner, actual_adapter, actual_source, text, request_id, metadata):
        admitted.append((actual_runner, actual_adapter, actual_source, text, request_id, metadata))
        return True

    monkeypatch.setattr("gateway.session_automation.admit_route_wake", admit_route_wake)

    await deliver_wake(adapter, source=source, text="Kanban task needs attention")

    assert admitted == [(runner, adapter, source, "Kanban task needs attention", "kanban-wake", {})]
