"""Busy bare-word approval replies must honor the slash-command access policy."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.event import MessageEvent
from gateway.run import GatewayRunner
from gateway.session import SessionSource


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "command", "user_id", "is_admin"), [
    ("yes", "approve", "guest", False),
    ("no", "deny", "guest", False),
    ("yes", "approve", "admin", True),
    ("no", "deny", "admin", True),
])
async def test_busy_plaintext_approval_obeys_admin_gate(monkeypatch, text, command, user_id, is_admin):
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(platforms={
        Platform.DISCORD: PlatformConfig(enabled=True, extra={"allow_admin_from": ["admin"]})
    })
    runner._session_key_for_source = lambda _source: "busy-session"
    adapter = MagicMock()
    adapter._unwrap_ephemeral.return_value = ("confirmation", None)
    runner._delivery_adapter_for = lambda _source: adapter
    runner._send_busy_reply = AsyncMock()
    approve = AsyncMock(return_value="approved")
    deny = AsyncMock(return_value="denied")
    runner._handle_approve_command = approve
    runner._handle_deny_command = deny
    source = SessionSource(platform=Platform.DISCORD, chat_id="chat", user_id=user_id)
    event = MessageEvent(text=text, source=source, message_id="reply", allow_gateway_control=True)
    monkeypatch.setattr("tools.approval.has_blocking_approval", lambda _session_key: True)

    handled = await runner._route_plaintext_approval_while_busy(event, "busy-session")

    assert handled is True
    expected_handler = approve if command == "approve" else deny
    other_handler = deny if command == "approve" else approve
    if is_admin:
        expected_handler.assert_awaited_once_with(event)
        other_handler.assert_not_awaited()
    else:
        approve.assert_not_awaited()
        deny.assert_not_awaited()
    runner._send_busy_reply.assert_awaited_once()
    if not is_admin:
        assert "admin" in runner._send_busy_reply.await_args.args[2].lower()
