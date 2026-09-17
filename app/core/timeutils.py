from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime; aware datetimes and ``None`` pass through."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
