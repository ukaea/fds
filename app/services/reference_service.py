from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, select

from app.core.timeutils import as_utc
from app.models.dataset import Dataset
from app.models.reference import ReferenceCoverage
from app.models.shot import Shot
from app.services.exceptions import FDSValidationError


@dataclass(frozen=True)
class ReferenceKind:
    """The ``Dataset`` attributes naming the roles a version provides
    (``roles_attr``) and the roles a signal uses (``references_attr``)."""

    name: str
    roles_attr: str
    references_attr: str


GEOMETRY = ReferenceKind("geometry", "geometry_roles", "geometry_references")
REFERENCE_KINDS: list[ReferenceKind] = [GEOMETRY]


def _as_coverage(applies_to: object) -> ReferenceCoverage:
    """Normalise a stored ``applies_to`` (JSON dict or model) to a model."""
    if applies_to is None:
        return ReferenceCoverage()
    return ReferenceCoverage.model_validate(applies_to)


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


class ReferenceService:
    """Resolution and write-validation for one :class:`ReferenceKind`."""

    def __init__(self, session: Session, kind: ReferenceKind) -> None:
        self.session = session
        self.kind = kind

    def _roles(self, dataset: Dataset) -> list[str]:
        return getattr(dataset, self.kind.roles_attr) or []

    def resolve(self, shot: Shot, roles: list[str]) -> dict[str, Dataset | None]:
        """Map each role to the version covering ``shot``, or ``None``. Only
        versions of the shot's own device are candidates."""
        versions = self._scope_versions(shot.device_name)
        resolved: dict[str, Dataset | None] = {}
        for role in roles:
            match: Dataset | None = None
            for version in versions:
                if role in self._roles(version) and self._covers(version, shot):
                    match = version
                    break
            resolved[role] = match
        return resolved

    def _covers(self, version: Dataset, shot: Shot) -> bool:
        coverage = _as_coverage(version.applies_to)
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

    def validate_new_version(
        self,
        device_name: str | None,
        roles: list[str] | None,
        applies_to: ReferenceCoverage | None,
        references: list[str] | None = None,
        shot_id: str | None = None,
        exclude_id: int | None = None,
    ) -> None:
        """Enforce this kind's write rules on a dataset.

        Reference data (``roles`` or ``references``) requires a device; a version
        (``roles``) must be device-level (no ``shot_id``). A version is also
        checked for range-endpoint integrity and per-role non-overlap with the
        device's other versions. ``exclude_id`` omits the dataset itself when
        re-validating.
        """
        if (roles or references) and device_name is None:
            raise FDSValidationError(
                f"{self.kind.name.capitalize()} data ({self.kind.roles_attr} / "
                f"{self.kind.references_attr}) requires a device: a global dataset "
                f"cannot host or reference it, since resolution is per-shot and "
                f"shots are device-scoped."
            )
        if roles and shot_id is not None:
            raise FDSValidationError(
                f"A {self.kind.name} version ({self.kind.roles_attr}) must be a "
                f"device-level dataset with no shot_id: reference data is "
                f"device-level bulk data shared across shots."
            )
        if not roles:
            return
        coverage = _as_coverage(applies_to)
        self._check_reference_integrity(device_name, coverage)

        existing = [
            version
            for version in self._scope_versions(device_name)
            if version.id != exclude_id
        ]
        for role in roles:
            for other in existing:
                if role not in self._roles(other):
                    continue
                if self._coverages_overlap(
                    device_name, coverage, _as_coverage(other.applies_to)
                ):
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} coverage for role "
                        f"'{role}' overlaps existing version (dataset "
                        f"id={other.id}); every shot must resolve to exactly one "
                        f"version."
                    )

    def validate_device_coverage(self, device_name: str) -> None:
        """Re-check integrity and per-role non-overlap across a device's versions."""
        versions = self._scope_versions(device_name)
        for version in versions:
            self._check_reference_integrity(
                device_name, _as_coverage(version.applies_to)
            )
        for index, version in enumerate(versions):
            version_coverage = _as_coverage(version.applies_to)
            for other in versions[index + 1 :]:
                shared_roles = set(self._roles(version)) & set(self._roles(other))
                if not shared_roles:
                    continue
                if self._coverages_overlap(
                    device_name, version_coverage, _as_coverage(other.applies_to)
                ):
                    role = sorted(shared_roles)[0]
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} coverage for role "
                        f"'{role}' overlaps between dataset ids {version.id} and "
                        f"{other.id} after this change."
                    )

    def check_shot_removable(self, device_name: str, shot_id: str) -> None:
        """Reject deletion of a shot referenced by any version of this kind."""
        for version in self._scope_versions(device_name):
            coverage = _as_coverage(version.applies_to)
            if shot_id in coverage.shots:
                raise FDSValidationError(
                    f"Shot '{shot_id}' is an explicit member of a "
                    f"{self.kind.name} version (dataset id={version.id}) and "
                    f"cannot be deleted."
                )
            for shot_range in coverage.shot_ranges:
                if shot_id in (shot_range.from_shot, shot_range.to_shot):
                    raise FDSValidationError(
                        f"Shot '{shot_id}' is a range endpoint of a "
                        f"{self.kind.name} version (dataset id={version.id}) and "
                        f"cannot be deleted."
                    )

    def _scope_versions(self, device_name: str | None) -> list[Dataset]:
        """Device-level datasets (``shot_id IS NULL``) of ``device_name`` that
        carry this kind's roles; empty for a ``None`` device."""
        if device_name is None:
            return []
        statement = select(Dataset).where(
            Dataset.device_name == device_name,
            col(Dataset.shot_id).is_(None),
        )
        return [
            version
            for version in self.session.exec(statement).all()
            if self._roles(version)
        ]

    def _shot_at(self, device_name: str | None, shot_id: str) -> datetime | None:
        shot = self.session.exec(
            select(Shot).where(Shot.device_name == device_name, Shot.id == shot_id)
        ).first()
        return as_utc(shot.shot_at) if shot else None

    def _check_reference_integrity(
        self, device_name: str | None, coverage: ReferenceCoverage
    ) -> None:
        for shot_range in coverage.shot_ranges:
            for endpoint in (shot_range.from_shot, shot_range.to_shot):
                if endpoint is None:
                    continue
                shot = self.session.exec(
                    select(Shot).where(
                        Shot.device_name == device_name, Shot.id == endpoint
                    )
                ).first()
                if shot is None:
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} range endpoint shot "
                        f"'{endpoint}' does not exist for device '{device_name}'."
                    )
                if shot.shot_at is None:
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} range endpoint shot "
                        f"'{endpoint}' has no shot_at."
                    )

    def _range_segments(
        self, device_name: str | None, coverage: ReferenceCoverage
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
        self, device_name: str | None, coverage: ReferenceCoverage
    ) -> list[_Segment]:
        """Point segments for a coverage's explicit shots that have a shot_at."""
        points: list[_Segment] = []
        for shot_id in coverage.shots:
            moment = self._shot_at(device_name, shot_id)
            if moment is not None:
                points.append(_Segment(moment, moment, end_inclusive=True))
        return points

    def _coverages_overlap(
        self,
        device_name: str | None,
        first: ReferenceCoverage,
        second: ReferenceCoverage,
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
