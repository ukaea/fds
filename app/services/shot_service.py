from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from app.models.shot import ShotRead

from sqlmodel import Session, select

from app.auth.access_control import get_effective_access_level
from app.auth.permissions import check_device_admin, check_shot_operator
from app.auth.security import AuthenticatedUser
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER
from app.models.policy import AccessLevel
from app.models.shot import Shot, ShotCreate, ShotUpdate
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ShotContextError,
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

        db_obj = Shot.model_validate(obj_in, update={"device_id": None})

        # Resolve device name to ID
        statement = select(Device).where(Device.name == target_device_name)
        device = self.session.exec(statement).first()
        if not device:
            raise DeviceNotFoundError(f"Device '{target_device_name}' not found")
        db_obj.device_id = device.id

        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def get_for_device(
        self,
        shot_id: str,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> Shot:
        """
        Retrieve a shot specifically for a device context.
        Raises ShotContextError if mismatch.
        """
        shot = self.get(shot_id)
        if not shot:
            raise ShotContextError(f"Shot '{shot_id}' not found")

        if not shot.device or shot.device.name != device_name:
            raise ShotContextError(
                f"Shot '{shot_id}' does not belong to device '{device_name}'"
            )

        self.check_read_access(shot, user)
        return shot

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

        # Filter permissions in python
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
        expected_device_name: str | None = None,
    ) -> Shot:
        """
        Update a shot. Enforces ownership and permission checks.
        """
        # 1. Context check (Ownership)
        if expected_device_name:
            if not db_obj.device or db_obj.device.name != expected_device_name:
                raise ShotContextError(f"Shot '{db_obj.id}' context mismatch")

        # 2. Permission check for the CURRENT device
        if db_obj.device:
            # Allow Shot Operators to update shots
            check_shot_operator(user, db_obj.device.name)
        else:
            # If for some reason it's orphaned, only fds-admin can touch it
            if "fds-admin" not in user.scopes:
                raise ForbiddenError("Only fds-admin can update orphaned shots")

        update_data = obj_in.model_dump(exclude_unset=True)

        # 3. Handle device change
        if "device_name" in update_data:
            new_device_name = update_data.pop("device_name")
            if new_device_name:
                # Permission check for the TARGET device
                check_device_admin(user, new_device_name)

                statement = select(Device).where(Device.name == new_device_name)
                device = self.session.exec(statement).first()
                if not device:
                    raise DeviceNotFoundError(f"Device '{new_device_name}' not found")
                db_obj.device_id = device.id
            else:
                db_obj.device_id = None

        db_obj.sqlmodel_update(update_data)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete_with_auth(
        self,
        shot_id: str,
        user: AuthenticatedUser,
        expected_device_name: str | None = None,
    ) -> bool:
        """
        Delete a shot with authentication and optional context check.
        """
        shot = self.get(shot_id)
        if not shot:
            return False

        if expected_device_name:
            if not shot.device or shot.device.name != expected_device_name:
                raise ShotContextError(f"Shot '{shot_id}' context mismatch")

        if shot.device:
            check_device_admin(user, shot.device.name)
        elif "fds-admin" not in user.scopes:
            raise ForbiddenError("Only fds-admin can delete orphaned shots")

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
