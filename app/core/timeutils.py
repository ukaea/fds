from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive datetime; aware datetimes and ``None`` pass through."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


UTCDatetime = Annotated[datetime, AfterValidator(as_utc)]
"""A datetime field. One given without an offset is taken to be UTC.

Columns store an instant, so a value has to say which zone it is in. Callers
that omit it have always meant UTC; this states that instead of rejecting them.
"""
