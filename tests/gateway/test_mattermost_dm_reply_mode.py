"""Mattermost direct messages stay in a single unthreaded session."""

import json
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base_thread_metadata import _thread_metadata_for_source
from gateway.session_context import source_route_metadata
from plugins.platforms.mattermost.adapter import MattermostAdapter


def _adapter():
    return MattermostAdapter(PlatformConfig(enabled=True, token="test-token", extra={
        "url": "https://mm.example.com",
    }))


@pytest.mark.asyncio
async def test_dm_thread_replies_keep_the_flat_session_and_delivery():
    adapter = _adapter()
    adapter._reply_mode = "thread"
    adapter._bot_user_id = "bot"
    adapter.handle_message = AsyncMock()

    event = {
        "event": "posted",
        "data": {
            "post": json.dumps({
                "id": "reply-post", "root_id": "old-thread-root", "user_id": "user",
                "channel_id": "dm-channel", "message": "follow up",
            }),
            "channel_type": "D",
        },
    }
    await adapter._handle_ws_event(event)

    source = adapter.handle_message.call_args.args[0].source
    assert source.chat_type == "dm"
    assert source.thread_id is None
    metadata = _thread_metadata_for_source(source, "reply-post")
    assert metadata == {"mattermost_is_dm": True}
    assert source_route_metadata(source, None) == {"mattermost_is_dm": True}

    adapter._api_post = AsyncMock(return_value={"id": "answer-post"})
    result = await adapter.send("dm-channel", "answer", reply_to="reply-post", metadata=metadata)

    assert result.success
    payload = adapter._api_post.call_args.args[1]
    assert "root_id" not in payload


def test_mattermost_channel_thread_metadata_does_not_mark_dm():
    source = _adapter().build_source(
        chat_id="channel", chat_type="channel", thread_id="thread-root")

    assert _thread_metadata_for_source(source) == {"thread_id": "thread-root"}
    assert source_route_metadata(source, {"thread_id": "thread-root"}) == {
        "thread_id": "thread-root",
    }
