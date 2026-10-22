"""Reap gateway-local CLI sessions whose only viewer disappeared with its process."""
import asyncio
import contextlib
import os


def _orphan_grace_seconds():
    """Use the existing dashboard orphan-reap grace and internal override."""
    raw = os.environ.get('HERMES_TUI_WS_ORPHAN_REAP_GRACE_S')
    if raw is None or not str(raw).strip():
        raw = None
        with contextlib.suppress(Exception):
            from hermes_cli.config import load_config
            raw = (load_config().get('dashboard') or {}).get('ws_orphan_reap_grace_s')
    with contextlib.suppress(ValueError, TypeError):
        return max(0.0, float(raw) if raw is not None else 20.0)
    return 20.0


def cancel_cli_orphan_close(authority, session_id):
    tasks = getattr(authority, '_cli_orphan_close_tasks', {})
    task = tasks.pop(session_id, None)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


def schedule_cli_orphan_close(authority, session_id):
    """End a CLI/oneshot session after the final transport closes, unless it reattaches first."""
    live = authority.sessions.get(session_id)
    if live is None or live.subscribers or authority.retiring or authority.retired:
        return
    platform = getattr(getattr(live.source, 'platform', None), 'value', None)
    if platform != 'local':
        return
    row = authority.db.get_session(session_id)
    if row is None or row.get('source') not in {'cli', 'oneshot'}:
        return
    grace = _orphan_grace_seconds()
    if grace == 0:
        return

    tasks = getattr(authority, '_cli_orphan_close_tasks', None)
    if tasks is None:
        tasks = authority._cli_orphan_close_tasks = {}
    previous = tasks.get(session_id)
    if previous is not None and not previous.done():
        previous.cancel()

    async def reap_if_still_unviewed():
        task = asyncio.current_task()
        try:
            await asyncio.sleep(grace)
            current = authority.sessions.get(session_id)
            if (tasks.get(session_id) is task and current is not None and not current.subscribers
                    and not authority.retiring and not authority.retired):
                from gateway.session_viewer_close import close_viewer_session
                await close_viewer_session(authority, session_id, 'cli_close')
        finally:
            if tasks.get(session_id) is task:
                tasks.pop(session_id, None)

    tasks[session_id] = asyncio.create_task(reap_if_still_unviewed())
