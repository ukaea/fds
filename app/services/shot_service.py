from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import distinct, func, true, tuple_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.auth.access_control import (
    check_read,
    get_effective_access_level,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_shot_operator
from app.core.context import ReadTier
from app.core.naming import normalise_device_name
from app.core.timeutils import as_utc
from app.models.available_properties import (
    AvailableProperties,
    PropertyValue,
    PropertyValues,
)
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.shot import Shot, ShotCreate, ShotRead, ShotUpdate
from app.services.annotation_service import AnnotationService
from app.services.available_properties import DEFAULT_MAX_VALUES, available_properties
from app.services.base_service import BaseService
from app.services.dataset_service import DatasetService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ResourceNotFoundError,
)
from app.services.filters import (
    entries_of,
    property_bound_clauses,
    property_clauses,
)
from app.services.jsonld import map_shot_to_dcat
from app.services.reference_service import REFERENCE_KINDS, ReferenceService
from app.services.visibility import read_page, readable_clause, readable_only

# Tolerance (seconds) when checking an explicit shot_duration against the
# shot_at/shot_end interval, so a whole-second duration is not rejected against a
# sub-second-precise interval.
_DURATION_TOLERANCE_S = 1.0


def validate_temporal_fields(
    shot_at: datetime | None,
    shot_end: datetime | None,
    shot_duration: float | None,
) -> None:
    """
    Enforce internal consistency of a shot's temporal fields.

    All three are optional, but when combinations are over-determined they must
    agree: a shot cannot end without starting, cannot end before it starts, cannot
    have a negative duration, and an explicit duration must match the start/end
    interval.
    """
    if shot_end is not None and shot_at is None:
        raise FDSValidationError("shot_end requires shot_at to be set.")

    shot_at = as_utc(shot_at)
    shot_end = as_utc(shot_end)

    if shot_at is not None and shot_end is not None and shot_end < shot_at:
        raise FDSValidationError("shot_end must not be before shot_at.")

    if shot_duration is not None and shot_duration < 0:
        raise FDSValidationError("shot_duration must not be negative.")

    if shot_at is not None and shot_end is not None and shot_duration is not None:
        interval = (shot_end - shot_at).total_seconds()
        if abs(interval - shot_duration) > _DURATION_TOLERANCE_S:
            raise FDSValidationError(
                f"shot_duration ({shot_duration}s) is inconsistent with the "
                f"shot_at/shot_end interval ({interval}s)."
            )


class ShotService(BaseService[Shot, ShotCreate, ShotUpdate]):
    def __init__(self, session: Session):
        super().__init__(Shot, session)

    def check_read_access(
        self,
        shot: Shot,
        user: AuthenticatedUser,
        tier: ReadTier = ReadTier.READ,
    ) -> None:
        """Enforce read access, and record it when the resource is not public."""
        check_read(shot, self.session, user, tier)

    def create(
        self,
        obj_in: ShotCreate,
        user: AuthenticatedUser,
        expected_device_name: str | None = None,
    ) -> Shot:
        """
        Create a new shot. Enforces device admin permissions and context consistency.
        """
        target_device_name = normalise_device_name(obj_in.device_name)
        expected_device_name = normalise_device_name(expected_device_name)

        if expected_device_name:
            if target_device_name and target_device_name != expected_device_name:
                raise ConflictError(
                    f"Device in context ({expected_device_name}) does not match device in body ({target_device_name})"
                )
            target_device_name = expected_device_name

        if not target_device_name:
            raise FDSValidationError("Device name is required for shot creation.")

        # Validate policy fields before any DB work
        validate_policy_fields(
            obj_in.access_level,
            obj_in.required_scopes,
            obj_in.allowed_idps,
        )
        validate_temporal_fields(
            obj_in.shot_at,
            obj_in.shot_end,
            obj_in.shot_duration,
        )

        # Permission check
        # Allow Shot Operators to create shots
        check_shot_operator(user, target_device_name)

        # Verify the device exists before creating the shot
        statement = select(Device).where(Device.name == target_device_name)
        if not self.session.exec(statement).first():
            raise DeviceNotFoundError(f"Device '{target_device_name}' not found")

        db_obj = Shot.model_validate(obj_in, update={"device_name": target_device_name})

        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(
                f"Shot '{obj_in.id}' already exists for device '{target_device_name}'"
            ) from e
        self.session.refresh(db_obj)
        return db_obj

    def get(self, id: Any) -> Shot | None:
        """
        Get a shot by its composite primary key as (device_name, shot_id).
        """
        if not isinstance(id, tuple) or len(id) != 2:
            raise FDSValidationError(
                "ShotService.get requires a composite key tuple (device_name, shot_id)."
            )
        device_name, shot_id = id

        statement = select(Shot).where(
            Shot.id == shot_id, Shot.device_name == normalise_device_name(device_name)
        )
        return self.session.exec(statement).first()

    def _resolve_shot(self, shot_id: str, device_name: str) -> Shot:
        """
        Internal helper: resolves a device name and shot ID to a Shot object.
        Raises DeviceNotFoundError or ResourceNotFoundError.
        """
        device = self.session.exec(
            select(Device).where(Device.name == normalise_device_name(device_name))
        ).first()
        if not device:
            raise DeviceNotFoundError(f"Device '{device_name}' not found")

        shot = self.get((device_name, shot_id))
        if not shot:
            raise ResourceNotFoundError(
                f"Shot '{shot_id}' not found for device '{device_name}'"
            )
        return shot

    def get_by_device_name(
        self, shot_id: str, device_name: str, user: AuthenticatedUser
    ) -> Shot:
        """
        Retrieve a single shot by device name and shot ID.
        Resolves the device, fetches the shot, and enforces read access.
        """
        shot = self._resolve_shot(shot_id, device_name)
        self.check_read_access(shot, user)
        return shot

    def get_multi_by_device_name(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
        properties: list[str] | None = None,
        minimums: list[str] | None = None,
        maximums: list[str] | None = None,
    ) -> Sequence[Shot]:
        """
        Retrieve all shots for a given device by its name.

        ``properties`` filters on entries in ``scientific_metadata``;
        several must all be present (see ``app.services.filters``).
        """
        device = normalise_device_name(device_name) or ""
        statement = (
            select(Shot)
            .where(*self._metadata_clauses(device, properties, minimums, maximums))
            .order_by(col(Shot.shot_at).desc().nullslast(), col(Shot.id).desc())
        )
        return read_page(
            self.session, Shot, statement, user, offset=offset, limit=limit
        )

    def _metadata_clauses(
        self,
        device: str,
        properties: list[str] | None,
        minimums: list[str] | None,
        maximums: list[str] | None,
    ) -> list[Any]:
        """The scope a filter describes, before access is applied.

        Shared by the listing and the properties so the two cannot drift: a count
        that does not match the rows it counts is worse than no count.
        """
        return [
            Shot.device_name == device,
            *property_clauses(Shot.scientific_metadata, properties),
            *property_bound_clauses(Shot.scientific_metadata, minimums, lower=True),
            *property_bound_clauses(Shot.scientific_metadata, maximums, lower=False),
        ]

    def _readable_scope(
        self,
        device_name: str,
        user: AuthenticatedUser,
        properties: list[str] | None = None,
        minimums: list[str] | None = None,
        maximums: list[str] | None = None,
    ) -> list[Any]:
        """The filtered scope, restricted to shots this caller may read."""
        device = normalise_device_name(device_name) or ""
        if not self.session.exec(select(Device).where(Device.name == device)).first():
            raise DeviceNotFoundError(f"Device '{device_name}' not found")

        where = self._metadata_clauses(device, properties, minimums, maximums)
        scope = select(Shot).where(*where)
        where.append(readable_clause(self.session, Shot, user, scope))
        return where

    def property_values(
        self,
        device_name: str,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        query: str | None = None,
        limit: int = 50,
    ) -> PropertyValues:
        """The values one name takes, with counts, for a vocabulary too big to list.

        Searched here rather than in the client: a device's `objective` runs to
        hundreds of values several hundred characters long, and shipping all of
        them to filter in a browser wastes the bandwidth the cap exists to save.
        """
        if not 1 <= limit <= 500:
            raise FDSValidationError(f"limit must be between 1 and 500, got {limit}.")

        where = self._readable_scope(device_name, user)
        entries = entries_of(col(Shot.scientific_metadata))
        entry_name = entries.c.value.op("->>")("name")
        entry_value = entries.c.value.op("->>")("value")
        conditions = [*where, entry_name == name, entry_value.is_not(None)]
        if query:
            conditions.append(entry_value.ilike(f"%{query}%"))

        rows = self.session.exec(
            select(
                entry_value.label("value"),
                func.count(distinct(tuple_(col(Shot.device_name), col(Shot.id)))).label(
                    "records"
                ),
            )
            .select_from(Shot)
            .join(entries, onclause=true())
            .where(*conditions)
            .group_by(entry_value)
            .order_by(
                func.count(
                    distinct(tuple_(col(Shot.device_name), col(Shot.id)))
                ).desc(),
                entry_value,
            )
            .limit(limit)
        ).all()

        total_distinct = self.session.exec(
            select(func.count(distinct(entry_value)))
            .select_from(Shot)
            .join(entries, onclause=true())
            .where(*conditions)
        ).one()

        return PropertyValues(
            name=name,
            distinct=total_distinct,
            values=[
                PropertyValue(value=value, records=records) for value, records in rows
            ],
        )

    def available_properties(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        properties: list[str] | None = None,
        minimums: list[str] | None = None,
        maximums: list[str] | None = None,
        max_values: int = DEFAULT_MAX_VALUES,
    ) -> AvailableProperties:
        """The properties a device's shots carry, for building a filter.

        Scoped by the same ``properties`` filter as the listing, so ``total``
        counts the matching shots this caller may read.
        """
        where = self._readable_scope(device_name, user, properties, minimums, maximums)
        return available_properties(
            self.session,
            Shot,
            col(Shot.scientific_metadata),
            where=where,
            max_values=max_values,
        )

    def update(
        self,
        *,
        shot_id: str,
        device_name: str,
        obj_in: ShotUpdate,
        user: AuthenticatedUser,
    ) -> Shot:
        """
        Update a shot. Resolves internally and enforces permission checks.
        """
        db_obj = self._resolve_shot(shot_id, device_name)

        # Permission check for the CURRENT device
        check_shot_operator(user, db_obj.device_name)

        update_data = obj_in.model_dump(exclude_unset=True)
        validate_policy_fields(
            update_data.get("access_level", db_obj.access_level),
            update_data.get("required_scopes", db_obj.required_scopes),
            update_data.get("allowed_idps", db_obj.allowed_idps),
        )
        validate_temporal_fields(
            update_data.get("shot_at", db_obj.shot_at),
            update_data.get("shot_end", db_obj.shot_end),
            update_data.get("shot_duration", db_obj.shot_duration),
        )

        # Handle device change - this is complex with composite PKs, effectively a move/copy
        # For now, we disallow changing device_name/device_id via update as it changes the PK
        if "device_name" in update_data:
            raise ConflictError(
                "Cannot change device context of an existing shot via update."
            )

        db_obj.sqlmodel_update(update_data)
        self.session.add(db_obj)

        # A shot_at change can shift coverage into another version's window;
        # re-validate every kind against the new value before committing.
        if "shot_at" in update_data:
            try:
                for kind in REFERENCE_KINDS:
                    ReferenceService(self.session, kind).validate_device_coverage(
                        db_obj.device_name
                    )
            except FDSValidationError:
                self.session.rollback()
                raise

        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete(
        self,
        shot_id: str,
        user: AuthenticatedUser,
        device_name: str,
    ) -> bool:
        """
        Delete a shot with authentication.
        """
        shot = self._resolve_shot(shot_id, device_name)

        check_device_admin(user, shot.device_name)

        # Block deletion of a shot that a reference-resource version depends on.
        for kind in REFERENCE_KINDS:
            ReferenceService(self.session, kind).check_shot_removable(
                shot.device_name, shot_id
            )

        self.session.delete(shot)
        self.session.commit()
        return True

    def to_read_model(
        self,
        shot: Shot,
        include_device: bool = False,
        include_annotations: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> "ShotRead":
        """
        Converts a Shot ORM object to a ShotRead DTO, optionally including the full device object.
        Centralises the presentation logic for shots. When ``include_annotations``
        is set, resolves the shot's shot-frame and device-frame properties,
        frame-scoped, so no dataset-frame properties leak in.
        """
        read_model = ShotRead.model_validate(shot)
        read_model.effective_access_level = get_effective_access_level(
            shot, self.session
        )
        if not include_device:
            read_model.device = None
        if include_annotations:
            dataset_service = DatasetService(self.session)
            annotations = readable_only(
                self.session, AnnotationService(self.session).for_shot(shot), user
            )
            read_model.annotations = [
                dataset_service.to_read_model(annotation) for annotation in annotations
            ] or None
        return read_model

    def to_dcat(
        self,
        shot: Shot,
        base_url: str,
        *,
        include_annotations: bool = False,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> dict[str, Any]:
        """Build the shot's DCAT/JSON-LD document, resolving its annotations into
        qualified relations."""
        enriched = self.to_read_model(
            shot, include_annotations=include_annotations, user=user
        )
        return map_shot_to_dcat(
            shot,
            base_url,
            annotations=enriched.annotations if include_annotations else None,
        )
