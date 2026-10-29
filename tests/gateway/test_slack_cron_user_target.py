"""Regression tests for Slack cron delivery targets."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.platforms.slack.adapter import SlackAdapter


@pytest.mark.asyncio
async def test_prefixed_user_id_target_opens_dm_for_live_delivery():
    adapter = SlackAdapter.__new__(SlackAdapter)
    adapter._dm_conversation_cache = {}
    client = MagicMock()
    client.conversations_open = AsyncMock(
        return_value={"ok": True, "channel": {"id": "D999NEW"}}
    )
    adapter._get_client = MagicMock(return_value=client)

    resolved = await adapter._ensure_dm_conversation("user:U123ABCDEF")

    assert resolved == "D999NEW"
    client.conversations_open.assert_awaited_once_with(users="U123ABCDEF")
