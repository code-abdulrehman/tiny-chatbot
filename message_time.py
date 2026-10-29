"""Timestamp helpers for message metadata (older chats may not have timestamps)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def timestamp_now():
    return datetime.now(timezone.utc).isoformat()


def display_time(timestamp, timezone_name=None):
    if not timestamp:
        return '—', 'Time was not recorded for this older message.'
    try:
        instant = datetime.fromisoformat(timestamp)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        local = instant.astimezone(ZoneInfo(timezone_name or 'UTC'))
        return local.strftime('%I:%M %p'), local.strftime('%Y-%m-%d %H:%M:%S %Z')
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return '—', 'Message time unavailable.'
