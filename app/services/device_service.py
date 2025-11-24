from sqlmodel import Session

from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.services.base_service import BaseService


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Device, session=session)
