from collections.abc import Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_device_admin, check_shot_operator
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot, ShotCreate, ShotRead, ShotUpdate
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)


class ShotService(BaseService[Shot, ShotCreate, ShotUpdate]):
    def __init__(self, session: Session):
        super().__init__(Shot, session)

    def _resolve_access(self, shot: Shot, user: AuthenticatedUser) -> str | None:
        """Canonical read-access resolution for a shot.

        Returns ``None`` when the user is permitted to read ``shot``.
        Returns a human-readable denial reason otherwise.

        This is the single source of truth that backs both ``check_read_access``
        (which raises) and ``is_accessible`` (which returns ``bool``).

        - PUBLIC: accessible to everyone.
        - RESTRICTED / EMBARGOED: must be authenticated; then IdP and scope
          gates if set. No capability check for metadata reads — that belongs
          to credential vending.
        """
        policy = get_effective_policy(shot, self.session)

        if policy.access_level == AccessLevel.PUBLIC:
            return None

        if user.is_anonymous:
            return "Authentication required for this resource"

        if policy.allowed_idps is not None:
            if user.issuer not in policy.allowed_idps:
                return (
                    "Access denied: your identity provider is not permitted "
                    "for this resource"
                )

        # None → auth gate only (already passed); [] → same; [...] → all must be present
        if policy.required_scopes is not None:
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    return f"Not authorized, requires scope: {scope}"

        return None

    def check_read_access(self, shot: Shot, user: AuthenticatedUser) -> None:
        """Raise ``ForbiddenError`` if ``user`` cannot read ``shot``.

        Used by single-resource endpoints to surface 403 responses with the
        denial reason.
        """
        reason = self._resolve_access(shot, user)
        if reason is not None:
            raise ForbiddenError(reason)

    def is_accessible(self, shot: Shot, user: AuthenticatedUser) -> bool:
        """Pure read-access predicate; returns ``True`` if ``user`` can read
        ``shot``, ``False`` otherwise. Never raises.

        Used by list filtering and the streaming export generator. The latter
        depends on this predicate being raise-free so a per-row failure cannot
        abort an in-flight HTTP response after headers have been sent.
        """
        return self._resolve_access(shot, user) is None

    def create(
        self,
        obj_in: ShotCreate,
        user: AuthenticatedUser,
        expected_device_name: str | None = None,
    ) -> Shot:
        """
        Create a new shot. Enforces device admin permissions and context consistency.
        """
        target_device_name = obj_in.device_name

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
            Shot.id == shot_id, Shot.device_name == device_name
        )
        return self.session.exec(statement).first()

    def _resolve_shot(self, shot_id: str, device_name: str) -> Shot:
        """
        Internal helper: resolves a device name and shot ID to a Shot object.
        Raises DeviceNotFoundError or ResourceNotFoundError.
        """
        device = self.session.exec(
            select(Device).where(Device.name == device_name)
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
    ) -> Sequence[Shot]:
        """
        Retrieve all shots for a given device by its name.
        """
        statement = (
            select(Shot)
            .where(Shot.device_name == device_name)
            .offset(offset)
            .limit(limit)
        )
        result = self.session.exec(statement).all()
        return [s for s in result if self.is_accessible(s, user)]

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

        # Handle device change - this is complex with composite PKs, effectively a move/copy
        # For now, we disallow changing device_name/device_id via update as it changes the PK
        if "device_name" in update_data:
            raise ConflictError(
                "Cannot change device context of an existing shot via update."
            )

        db_obj.sqlmodel_update(update_data)
        self.session.add(db_obj)
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

        check_device_admin(user, device_name)

        self.session.delete(shot)
        self.session.commit()
        return True

    def to_read_model(self, shot: Shot, include_device: bool = False) -> "ShotRead":
        """
        Converts a Shot ORM object to a ShotRead DTO, optionally including the full device object.
        Centralizes the presentation logic for shots.
        """
        read_model = ShotRead.model_validate(shot)
        read_model.effective_access_level = get_effective_access_level(
            shot, self.session
        )
        if not include_device:
            read_model.device = None
        return read_model
