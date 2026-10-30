"""Session-fork endpoint logic for the API server."""

import asyncio
import re
import time
import uuid
from contextlib import suppress
from typing import Any


async def handle_fork_session(adapter, request: Any, error_response) -> Any:
    """Create a visible branch and preserve the source transcript."""
    from aiohttp import web

    source_id = request.match_info["session_id"]
    source, err = await adapter._get_existing_session_or_404(source_id)
    if err:
        return err
    body, err = await adapter._read_json_body(request)
    if err:
        return err
    db = await adapter._ensure_session_db_async()
    fork_id = str(body.get("id") or body.get("session_id") or f"api_{int(time.time())}_{uuid.uuid4().hex[:8]}").strip()
    if not fork_id or re.search(r'[\r\n\x00]', fork_id):
        return error_response("Invalid session ID", 400, code="invalid_session_id")
    if await asyncio.to_thread(db.get_session, fork_id):
        return error_response(f"Session already exists: {fork_id}", 409, code="session_exists")

    # Create the child before ending the parent, so failed creation leaves the source intact (#11030).
    # _branched_from is the durable marker needed because the child starts before the parent ends.
    await asyncio.to_thread(
        db.create_session, fork_id, "api_server", model=source.get("model"),
        system_prompt=source.get("system_prompt"), parent_session_id=source_id,
        model_config={"_branched_from": source_id})
    await asyncio.to_thread(db.end_session, source_id, "branched")
    messages = await asyncio.to_thread(db.get_messages, source_id)
    await asyncio.to_thread(db.replace_messages, fork_id, messages)
    # Copied message timestamps can be old; stamp the new fork so it appears recent in listings.
    await asyncio.to_thread(db.touch_session_activity, fork_id)
    title = body.get("title")
    if title is None:
        base = source.get("title") or "fork"
        title = f"{base} fork"
        with suppress(Exception):
            title = await asyncio.to_thread(db.get_next_title_in_lineage, base)
    try:
        await asyncio.to_thread(db.set_session_title, fork_id, str(title))
    except ValueError as exc:
        return error_response(str(exc), 400, code="invalid_title")
    fork = await asyncio.to_thread(db.get_session, fork_id) or {"id": fork_id, "parent_session_id": source_id}
    return web.json_response(
        {"object": "hermes.session", "session": adapter._session_response(fork)}, status=201)
