from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.models.coverage import Coverage
from app.models.dataset import Dataset
from app.models.shot import Shot
from app.services.coverage import CoverageMatcher, as_coverage
from app.services.exceptions import FDSValidationError


@dataclass(frozen=True)
class ReferenceKind:
    """The ``Dataset`` attributes naming the roles a version provides
    (``roles_attr``) and the roles a signal uses (``references_attr``).

    ``order_attr`` names an integer attribute that orders a role's versions into
    a chain (calibration stages); when set, a role resolves to an ordered *list*
    of versions and non-overlap holds per ``(role, order)``. ``None`` is the
    single-stage case (geometry): one version per role.
    """

    name: str
    roles_attr: str
    references_attr: str
    order_attr: str | None = None


GEOMETRY = ReferenceKind("geometry", "geometry_roles", "geometry_references")
CALIBRATION = ReferenceKind(
    "calibration",
    "calibration_roles",
    "calibration_references",
    order_attr="calibration_stage",
)
REFERENCE_KINDS: list[ReferenceKind] = [GEOMETRY, CALIBRATION]


class ReferenceService:
    """Resolution and write-validation for one :class:`ReferenceKind`.

    Handles the reference kinds (geometry, calibration): device-level *versions*
    discovered by a signal's role reference and selected per shot by coverage.
    """

    def __init__(self, session: Session, kind: ReferenceKind) -> None:
        self.session = session
        self.kind = kind
        self.coverage = CoverageMatcher(session)

    def _roles(self, dataset: Dataset) -> list[str]:
        return getattr(dataset, self.kind.roles_attr) or []

    def _order_key(self, version: Dataset) -> int | None:
        """The version's position in its chain, or ``None`` for a single-stage
        kind (all versions then share the one bucket)."""
        if self.kind.order_attr is None:
            return None
        return getattr(version, self.kind.order_attr)

    def _role_scope(self, role: str, order: int | None) -> str:
        """Human phrase for the non-overlap key, e.g. ``role 'gain' at stage 2``."""
        if self.kind.order_attr is None:
            return f"role '{role}'"
        return f"role '{role}' at stage {order}"

    def _one_version_rule(self) -> str:
        if self.kind.order_attr is None:
            return "every shot must resolve to exactly one version."
        return "every shot must resolve to exactly one version per stage."

    def _covering(
        self, versions: list[Dataset], role: str, shot: Shot
    ) -> list[Dataset]:
        """Versions that provide ``role`` and cover ``shot``, ordered by the
        kind's stage (ascending) when it has one."""
        matches = [
            version
            for version in versions
            if role in self._roles(version)
            and self.coverage.covers_version(version, shot)
        ]
        if self.kind.order_attr is not None:
            matches.sort(key=lambda version: self._order_key(version) or 0)
        return matches

    def resolve(self, shot: Shot, roles: list[str]) -> dict[str, Dataset | None]:
        """Map each role to the single version covering ``shot``, or ``None``.
        Only versions of the shot's own device are candidates. For an ordered
        kind this is the earliest stage; use :meth:`resolve_chain` for the chain."""
        versions = self._scope_versions(shot.device_name)
        return {
            role: next(iter(self._covering(versions, role, shot)), None)
            for role in roles
        }

    def resolve_chain(self, shot: Shot, roles: list[str]) -> dict[str, list[Dataset]]:
        """Map each role to the ordered chain of versions covering ``shot`` (by
        ascending stage); an empty list when none apply."""
        versions = self._scope_versions(shot.device_name)
        return {role: self._covering(versions, role, shot) for role in roles}

    def validate_new_version(
        self,
        device_name: str | None,
        roles: list[str] | None,
        applies_to: Coverage | None,
        order: int | None = None,
        references: list[str] | None = None,
        shot_id: str | None = None,
        exclude_id: int | None = None,
    ) -> None:
        """Enforce this kind's write rules on a dataset.

        Reference data (``roles`` or ``references``) requires a device; a version
        (``roles``) must be device-level (no ``shot_id``). A version is also
        checked for range-endpoint integrity and per-``(role, order)`` non-overlap
        with the device's other versions; for a single-stage kind ``order`` is
        ``None`` and the check is simply per-role. ``exclude_id`` omits the
        dataset itself when re-validating.
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
        coverage = as_coverage(applies_to)
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
                if self._order_key(other) != order:
                    continue
                if self.coverage.overlaps(
                    device_name, coverage, as_coverage(other.applies_to)
                ):
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} coverage for "
                        f"{self._role_scope(role, order)} overlaps existing "
                        f"version (dataset id={other.id}); {self._one_version_rule()}"
                    )

    def validate_device_coverage(self, device_name: str) -> None:
        """Re-check integrity and per-role non-overlap across a device's versions."""
        versions = self._scope_versions(device_name)
        for version in versions:
            self._check_reference_integrity(
                device_name, as_coverage(version.applies_to)
            )
        for index, version in enumerate(versions):
            version_coverage = as_coverage(version.applies_to)
            for other in versions[index + 1 :]:
                if self._order_key(version) != self._order_key(other):
                    continue
                shared_roles = set(self._roles(version)) & set(self._roles(other))
                if not shared_roles:
                    continue
                if self.coverage.overlaps(
                    device_name, version_coverage, as_coverage(other.applies_to)
                ):
                    role = sorted(shared_roles)[0]
                    raise FDSValidationError(
                        f"{self.kind.name.capitalize()} coverage for "
                        f"{self._role_scope(role, self._order_key(version))} "
                        f"overlaps between dataset ids {version.id} and "
                        f"{other.id} after this change."
                    )

    def check_shot_removable(self, device_name: str, shot_id: str) -> None:
        """Reject deletion of a shot referenced by any version of this kind."""
        for version in self._scope_versions(device_name):
            coverage = as_coverage(version.applies_to)
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

    def _check_reference_integrity(
        self, device_name: str | None, coverage: Coverage
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
