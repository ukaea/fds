from collections.abc import Sequence
from sqlmodel import Session, select

from app.models.device import Device, DeviceCreate, DeviceUpdate


class DeviceService:
    def __init__(self, session: Session):
        self.session = session

    def create_device(self, device_create: DeviceCreate) -> Device:
        device = Device.model_validate(device_create)
        self.session.add(device)
        self.session.commit()
        self.session.refresh(device)
        return device

    def get_device(self, device_id: int) -> Device | None:
        return self.session.get(Device, device_id)

    def get_devices(self, offset: int = 0, limit: int = 100) -> Sequence[Device]:
        statement = select(Device).offset(offset).limit(limit)
        results = self.session.exec(statement)
        devices = results.all()
        return devices

    def update_device(
        self, device_id: int, device_update: DeviceUpdate
    ) -> Device | None:
        device = self.session.get(Device, device_id)
        if not device:
            return None

        update_data = device_update.model_dump(exclude_unset=True)
        device.sqlmodel_update(update_data)
        self.session.add(device)
        self.session.commit()
        self.session.refresh(device)
        return device

    def delete_device(self, device_id: int) -> bool:
        device = self.session.get(Device, device_id)
        if not device:
            return False
        self.session.delete(device)
        self.session.commit()
        return True
