from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from app.core.timeutils import as_utc
from app.models.coverage import Coverage
from app.models.dataset import Dataset
from app.models.shot import Shot


def as_coverage(applies_to: object) -> Coverage:
    """Normalise a stored ``applies_to`` (JSON dict or model) to a ``Coverage``."""
    if applies_to is None:
        return Coverage()
    return Coverage.model_validate(applies_to)


@dataclass(frozen=True)
class _Segment:
    """A timeline window ``[start, end]`` or ``[start, end)``. ``start`` is
    inclusive; ``end_inclusive`` sets whether ``end`` is; ``None`` is unbounded."""

    start: datetime | None
    end: datetime | None
    end_inclusive: bool

    def contains(self, moment: datetime) -> bool:
        if self.start is not None and moment < self.start:
            return False
        if self.end is not None:
            return moment <= self.end if self.end_inclusive else moment < self.end
        return True

    def overlaps(self, other: "_Segment") -> bool:
        self_starts_before_other_ends = (
            self.start is None
            or other.end is None
            or (
                self.start <= other.end
                if other.end_inclusive
                else self.start < other.end
            )
        )
        other_starts_before_self_ends = (
            other.start is None
            or self.end is None
            or (
                other.start <= self.end
                if self.end_inclusive
                else other.start < self.end
            )
        )
        return self_starts_before_other_ends and other_starts_before_self_ends


class CoverageMatcher:
    """Whether a shot coverage (``applies_to``) includes a shot, and whether two
    coverages overlap. Shared by every shot-ranged dataset relationship: reference
    versions (geometry, calibration) and device-level annotations all resolve by
    the same coverage rules.

    Shot-range endpoints resolve to their ``shot_at`` at read time; date ranges are
    literal half-open windows; explicit shots match by id, or by ``shot_at`` when
    testing overlap.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def covers_version(self, version: Dataset, shot: Shot) -> bool:
        """Whether ``version``'s ``applies_to`` includes ``shot``."""
        return self.covers(as_coverage(version.applies_to), shot)

    def covers(self, coverage: Coverage, shot: Shot) -> bool:
        if shot.id in coverage.shots:
            return True
        shot_at = as_utc(shot.shot_at)
        if shot_at is None:
            # Without shot_at only explicit membership can match.
            return False
        for segment in self._range_segments(shot.device_name, coverage):
            if segment.contains(shot_at):
                return True
        return False

    def overlaps(
        self, device_name: str | None, first: Coverage, second: Coverage
    ) -> bool:
        if set(first.shots) & set(second.shots):
            return True
        first_segments = self._range_segments(
            device_name, first
        ) + self._point_segments(device_name, first)
        second_segments = self._range_segments(
            device_name, second
        ) + self._point_segments(device_name, second)
        for segment in first_segments:
            for other_segment in second_segments:
                if segment.overlaps(other_segment):
                    return True
        return False

    def _shot_at(self, device_name: str | None, shot_id: str) -> datetime | None:
        shot = self.session.exec(
            select(Shot).where(Shot.device_name == device_name, Shot.id == shot_id)
        ).first()
        return as_utc(shot.shot_at) if shot else None

    def _range_segments(
        self, device_name: str | None, coverage: Coverage
    ) -> list[_Segment]:
        """Segments for a coverage's shot ranges and date ranges, not its shots."""
        segments: list[_Segment] = []
        for shot_range in coverage.shot_ranges:
            start = self._shot_at(device_name, shot_range.from_shot)
            end = (
                self._shot_at(device_name, shot_range.to_shot)
                if shot_range.to_shot is not None
                else None
            )
            if shot_range.from_shot is not None and start is None:
                continue
            segments.append(_Segment(start, end, end_inclusive=True))
        for date_range in coverage.date_ranges:
            segments.append(
                _Segment(
                    as_utc(date_range.from_date),
                    as_utc(date_range.to_date),
                    end_inclusive=False,
                )
            )
        return segments

    def _point_segments(
        self, device_name: str | None, coverage: Coverage
    ) -> list[_Segment]:
        """Point segments for a coverage's explicit shots that have a shot_at."""
        points: list[_Segment] = []
        for shot_id in coverage.shots:
            moment = self._shot_at(device_name, shot_id)
            if moment is not None:
                points.append(_Segment(moment, moment, end_inclusive=True))
        return points
