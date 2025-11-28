from typing import Sequence

from sqlmodel import Session, select

from app.models.device import Device
from app.models.shot import Shot, ShotCreate, ShotUpdate
from app.services.base_service import BaseService
from app.services.exceptions import DeviceNotFoundError


class ShotService(BaseService[Shot, ShotCreate, ShotUpdate]):
    def __init__(self, session: Session):
        super().__init__(Shot, session)

    def create(self, obj_in: ShotCreate) -> Shot:
        """
        Create a new shot, ensuring the device exists.
        """
        # Check if device exists
        device = self.session.get(Device, obj_in.device_id)
        if not device:
            raise DeviceNotFoundError(f"Device with id {obj_in.device_id} not found")

        # Proceed with creation using parent method's logic
        db_obj = self.model.model_validate(obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def get_multi_by_device(self, device_id: int, offset: int = 0, limit: int = 100) -> Sequence[Shot]:
        """
        Get multiple shots for a specific device with pagination.
        """
        statement = (
            select(Shot)
            .where(Shot.device_id == device_id)
            .offset(offset)
            .limit(limit)
        )
        result = self.session.exec(statement)
        shots = result.all()
        return shots