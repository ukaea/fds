from collections.abc import Sequence
from sqlmodel import Session, select

from app.models.shot import Shot, ShotCreate
from app.services.device_service import DeviceService


class ShotService:
    def __init__(self, session: Session):
        self.session = session

    def create_shot(self, shot_create: ShotCreate) -> Shot | None:
        # Ensure the device exists before creating the shot
        device_service = DeviceService(self.session)
        if not device_service.get_device(shot_create.device_id):
            return None

        shot = Shot.model_validate(shot_create)
        self.session.add(shot)
        self.session.commit()
        self.session.refresh(shot)
        return shot

    def get_shot(self, shot_id: int) -> Shot | None:
        return self.session.get(Shot, shot_id)

    def get_shots(self, offset: int = 0, limit: int = 100) -> Sequence[Shot]:
        statement = select(Shot).offset(offset).limit(limit)
        results = self.session.exec(statement)
        shots = results.all()
        return shots

    def get_shots_for_device(
        self, device_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Shot]:
        statement = select(Shot).where(Shot.device_id == device_id).offset(offset).limit(limit)
        results = self.session.exec(statement)
        device_shots = results.all()
        return device_shots

    def delete_shot(self, shot_id: int) -> bool:
        shot = self.session.get(Shot, shot_id)
        if not shot:
            return False
        self.session.delete(shot)
        self.session.commit()
        return True
