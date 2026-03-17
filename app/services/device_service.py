from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.access_control import (
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_is_admin
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.base_service import BaseService
from app.services.exceptions import ConflictError, ForbiddenError


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Device, session=session)

    def check_read_access(self, device: Device, user: AuthenticatedUser) -> None:
        """Enforce read access for device metadata."""
        policy = get_effective_policy(device, self.session)

        if policy.access_level == AccessLevel.PUBLIC:
            return

        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

        if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
            raise ForbiddenError(
                "Access denied: your identity provider is not permitted "
                "for this resource"
            )

        if policy.required_scopes is not None:
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    raise ForbiddenError(f"Not authorized, requires scope: {scope}")

    def get_multi(
        self,
        *,
        user: AuthenticatedUser | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Device]:
        """Get devices with metadata visibility filtering applied."""
        devices = list(super().get_multi(offset=offset, limit=limit))
        if user is None:
            return devices

        accessible_devices: list[Device] = []

        for device in devices:
            try:
                self.check_read_access(device, user)
                accessible_devices.append(device)
            except ForbiddenError:
                continue

        return accessible_devices

    def get_by_name(self, name: str) -> Device | None:
        result = self.session.exec(select(Device).where(Device.name == name))
        return result.first()

    def create(self, obj_in: DeviceCreate, user: AuthenticatedUser) -> Device:
        """
        Create a new device. Requires global admin privileges.
        """
        validate_policy_fields(
            obj_in.access_level,
            obj_in.required_scopes,
            obj_in.allowed_idps,
        )
        check_is_admin(user)
        try:
            return self.create_unchecked(obj_in)
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(f"Device '{obj_in.name}' already exists") from e

    def update(
        self, *, db_obj: Device, obj_in: DeviceUpdate, user: AuthenticatedUser
    ) -> Device:
        """
        Update a device. Requires global admin privileges.
        """
        check_is_admin(user)
        update_data = obj_in.model_dump(exclude_unset=True)
        validate_policy_fields(
            update_data.get("access_level", db_obj.access_level),
            update_data.get("required_scopes", db_obj.required_scopes),
            update_data.get("allowed_idps", db_obj.allowed_idps),
        )
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, device_name: str, user: AuthenticatedUser) -> bool:
        """
        Delete a device by name. Requires global admin privileges.
        """
        check_is_admin(user)
        device = self.get_by_name(device_name)
        if not device:
            return False
        self.session.delete(device)
        self.session.commit()
        return True

    def to_read_model(self, device: Device) -> DeviceRead:
        """
        Converts a Device ORM object to a DeviceRead DTO, including the effective access level.
        """
        read_model = DeviceRead.model_validate(device)
        read_model.effective_access_level = get_effective_access_level(
            device, self.session
        )
        return read_model
