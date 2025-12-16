from sqlmodel import Session, select

from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.services.base_service import BaseService


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Device, session=session)
    def get_by_name(self, name: str) -> Device | None:
        """
        Get a device by its name.
        """
        result = self.session.exec(select(Device).where(Device.name == name))
        return result.first()
