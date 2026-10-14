"""Thread and platform routing metadata shared by gateway adapter sends."""


def _thread_metadata_for_source(source, reply_to_message_id: str | None = None) -> dict | None:
    """Build outbound routing metadata from a normalized session source.

    Telegram DM topics route with ``message_thread_id`` plus a reply anchor. Mattermost DMs
    carry an explicit marker because their replies must remain flat even when channel threading
    is enabled.
    """
    thread_id = getattr(source, "thread_id", None)
    platform = getattr(getattr(source, "platform", None), "value", getattr(source, "platform", None))
    platform = str(platform or "").lower()
    metadata = {"thread_id": thread_id} if thread_id is not None else {}
    # Slack workspace identity is routing state: carry it so a multi-workspace Socket Mode
    # gateway never falls back to its primary WebClient.
    scope_id = getattr(source, "scope_id", None) if platform == "slack" else None
    if scope_id:
        metadata["slack_team_id"] = str(scope_id)
    if platform == "mattermost" and getattr(source, "chat_type", None) == "dm":
        metadata["mattermost_is_dm"] = True
    if not metadata:
        return None
    if platform == "telegram" and getattr(source, "chat_type", None) == "dm":
        metadata["telegram_dm_topic_reply_fallback"] = True
        if str(thread_id) not in {"", "1"}:
            metadata["direct_messages_topic_id"] = str(thread_id)
        anchor = reply_to_message_id or getattr(source, "message_id", None)
        if anchor is not None:
            metadata["telegram_reply_to_message_id"] = str(anchor)
    # Routed profile (multiplex / profile_routes): outbound prune paths must not assume the
    # adapter's static profile stamp.
    profile = str(getattr(source, "profile", None) or "").strip()
    if profile:
        metadata["hermes_profile"] = profile
    return metadata
