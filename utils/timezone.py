"""Timezone utilities for consistent datetime handling.

All datetimes stored as UTC in DB.
Display and date boundaries use Asia/Shanghai (Beijing time, UTC+8).
"""

from datetime import date, datetime, timezone, timedelta

BJT_OFFSET = timedelta(hours=8)


def ensure_utc(dt: datetime | None) -> datetime | None:
    """If dt is naive, assume it's UTC. Returns a timezone-aware datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def ensure_bjt(dt: datetime | None) -> datetime | None:
    """Convert a datetime to Asia/Shanghai (BJT) for display."""
    if dt is None:
        return None
    dt = ensure_utc(dt)
    return dt.astimezone(timezone(BJT_OFFSET))


def now_bjt() -> datetime:
    """Current time in Beijing timezone."""
    return datetime.now(timezone.utc).astimezone(timezone(BJT_OFFSET))


def today_bjt() -> date:
    """Current date in Beijing timezone."""
    from datetime import date
    return now_bjt().date()


def iso_utc(dt: datetime | None) -> str | None:
    """Serialize a datetime as ISO 8601 with UTC timezone info."""
    if dt is None:
        return None
    dt = ensure_utc(dt)
    return dt.isoformat()
