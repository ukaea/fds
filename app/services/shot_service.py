from collections.abc import Sequence
from sqlmodel import Session, select

from app.models.shot import Shot, ShotCreate, ShotUpdate
from app.services.base_service import BaseService
from app.services.device_service import DeviceService


class ShotService(BaseService[Shot, ShotCreate, ShotUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Shot, session=session)

    def create(self, obj_in: ShotCreate) -> Shot:
        # Ensure the device exists before creating the shot
        device_service = DeviceService(self.session)
        if not device_service.get(obj_in.device_id):
            raise ValueError(f"Device with id {obj_in.device_id} not found")

        return super().create(obj_in)

    def get_shots_for_device(
        self, device_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Shot]:
        statement = (
            select(Shot).where(Shot.device_id == device_id).offset(offset).limit(limit)
        )
        results = self.session.exec(statement)
        device_shots = results.all()
        return device_shots
