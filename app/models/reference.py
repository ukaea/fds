from datetime import datetime

from sqlmodel import SQLModel


class ShotRange(SQLModel):
    """A window bounded by endpoint shot ids, both inclusive. Endpoints resolve
    to their ``shot_at``; ``to_shot=None`` is open-ended."""

    from_shot: str
    to_shot: str | None = None


class DateRange(SQLModel):
    """A half-open ``[from_date, to_date)`` window; ``to_date=None`` is open-ended."""

    from_date: datetime
    to_date: datetime | None = None


class ReferenceCoverage(SQLModel):
    """The shots a version covers: the union of ``shots``, ``shot_ranges``, and
    ``date_ranges``."""

    shots: list[str] = []
    shot_ranges: list[ShotRange] = []
    date_ranges: list[DateRange] = []
