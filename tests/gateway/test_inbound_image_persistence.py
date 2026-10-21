"""Image turns keep renderable attachment refs in the persisted user row."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.run import GatewayRunner
from gateway.session import SessionSource
from gateway.config import Platform
from gateway.platforms.event import MessageEvent, MessageType


@pytest.mark.asyncio
async def test_text_routed_image_persists_caption_and_ref_not_vision_enrichment(monkeypatch, tmp_path):
    image = tmp_path / "screenshot.png"
    image.write_bytes(b"image")
    source = SessionSource(
        platform=Platform.API_SERVER, chat_id="desktop-session", chat_type="dm", user_id="desktop",
    )
    event = MessageEvent(
        text="What is in this screenshot?", message_type=MessageType.PHOTO, source=source,
        media_urls=[str(image)], media_types=["image/png"],
    )
    runner = object.__new__(GatewayRunner)
    runner._consume_pending_native_image_paths = lambda _session_key: []
    runner._prefix_inbound_sender_context = lambda _event, _source, text: text
    runner._classify_inbound_media = lambda _event, _pending: ([str(image)], [], [], [])
    runner._enrich_inbound_images = AsyncMock(return_value="[The user sent an image~ vision-only description]")
    runner._prepend_inbound_media_file_notes = lambda text, *_paths: text
    runner._prepend_inbound_document_notes = lambda _event, text: text
    runner._prepend_inbound_reply_context = lambda _event, _source, text: text

    async def no_context_refs(_runner, _event, _source, _session_key, text):
        return text

    monkeypatch.setattr("gateway.run_inbound.rehome_inbound_media", lambda _event: None)
    monkeypatch.setattr("gateway.session_context_refs.turn_references", no_context_refs)
    monkeypatch.setattr("gateway.run._load_gateway_config", dict)
    monkeypatch.setattr("gateway.run._message_timestamps_enabled", lambda _config: False)

    model_text = await runner._prepare_inbound_message_text(
        event=event, source=source, history=[], session_key="desktop-session",
    )
    _rendered, persisted, _timestamp = runner._hmwa_apply_message_timestamp(event, model_text)

    assert model_text == "[The user sent an image~ vision-only description]"
    assert persisted == f"What is in this screenshot?\n@image:{image}"
