from sqlmodel import Session, select

from app.models.device import Device, DeviceCreate, DeviceUpdate, DeviceRead
from app.services.base_service import BaseService
from app.auth.security import AuthenticatedUser
from app.auth.permissions import check_is_admin
from app.auth.access_control import get_effective_access_level


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Device, session=session)

    def get_by_name(self, name: str) -> Device | None:
        result = self.session.exec(select(Device).where(Device.name == name))
        return result.first()

    def create(self, obj_in: DeviceCreate, user: AuthenticatedUser) -> Device:
        """
        Create a new device. Requires global admin privileges.
        """
        check_is_admin(user)
        return super().create(obj_in)

    def update(
        self, *, db_obj: Device, obj_in: DeviceUpdate, user: AuthenticatedUser
    ) -> Device:
        """
        Update a device. Requires global admin privileges.
        """
        check_is_admin(user)
        return super().update(db_obj=db_obj, obj_in=obj_in)

    def delete(self, device_id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a device. Requires global admin privileges.
        """
        check_is_admin(user)
        db_obj = self.get(device_id)
        if not db_obj:
            return False
        self.session.delete(db_obj)
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
