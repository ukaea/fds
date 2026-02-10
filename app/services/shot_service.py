from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from app.models.shot import ShotRead

from sqlmodel import Session, select

from app.auth.access_control import get_effective_access_level
from app.auth.permissions import check_device_admin, check_shot_operator
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot, ShotCreate, ShotUpdate
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
)


class ShotService(BaseService[Shot, ShotCreate, ShotUpdate]):
    def __init__(self, session: Session):
        super().__init__(Shot, session)

    def check_read_access(self, shot: Shot, user: AuthenticatedUser) -> None:
        """
        Enforces read access rules:
        - PUBLIC: Allow anonymous.
        - RESTRICTED: Allow authenticated.
        - EMBARGOED: Allow authenticated (for now, usually requires specific scope).
        """
        level = get_effective_access_level(shot, self.session)
        if level == AccessLevel.PUBLIC:
            return

        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

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

        # Permission check
        # Allow Shot Operators to create shots
        check_shot_operator(user, target_device_name)

        # Resolve device name to ID
        statement = select(Device).where(Device.name == target_device_name)
        device = self.session.exec(statement).first()
        if not device:
            raise DeviceNotFoundError(f"Device '{target_device_name}' not found")

        db_obj = Shot.model_validate(obj_in, update={"device_id": device.id})

        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def get(self, shot_id: str, device_id: int) -> Shot | None:
        """
        Get a shot by its composite primary key (shot_id, device_id).
        """
        statement = select(Shot).where(Shot.id == shot_id, Shot.device_id == device_id)
        return self.session.exec(statement).first()

    def get_multi_by_device(
        self, device_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Shot]:
        statement = (
            select(Shot).where(Shot.device_id == device_id).offset(offset).limit(limit)
        )
        result = self.session.exec(statement)
        return result.all()

    def get_multi_by_device_name(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Shot]:
        """
        Retrieve all shots for a given device by its unique name.
        """
        # We join with device to filter by name
        statement = (
            select(Shot)
            .join(Device)
            .where(Device.name == device_name)
            .offset(offset)
            .limit(limit)
        )
        result = self.session.exec(statement).all()

        # Filter permissions
        accessible_shots = []
        for s in result:
            try:
                self.check_read_access(s, user)
                accessible_shots.append(s)
            except ForbiddenError:
                continue

        return accessible_shots

    def update(
        self,
        *,
        db_obj: Shot,
        obj_in: ShotUpdate,
        user: AuthenticatedUser,
    ) -> Shot:
        """
        Update a shot. Enforces ownership and permission checks.
        """
        # Permission check for the CURRENT device
        if db_obj.device:
            check_shot_operator(user, db_obj.device.name)

        update_data = obj_in.model_dump(exclude_unset=True)

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

    def delete_with_auth(
        self,
        shot_id: str,
        user: AuthenticatedUser,
        device_name: str,
    ) -> bool:
        """
        Delete a shot with authentication. Device name is now required to identify the shot.
        """
        # Resolve device name to ID
        statement = select(Device).where(Device.name == device_name)
        device = self.session.exec(statement).first()
        if not device:
            return False  # or raise DeviceNotFoundError

        shot = self.get(shot_id, device.id)
        if not shot:
            return False

        check_device_admin(user, device_name)

        self.session.delete(shot)
        self.session.commit()
        return True

    def to_read_model(self, shot: Shot, include_device: bool = False) -> "ShotRead":
        """
        Converts a Shot ORM object to a ShotRead DTO, optionally including the full device object.
        Centralizes the presentation logic for shots.
        """
        from app.models.shot import ShotRead

        read_model = ShotRead.model_validate(shot)
        read_model.effective_access_level = get_effective_access_level(
            shot, self.session
        )
        if not include_device:
            read_model.device = None
        return read_model
