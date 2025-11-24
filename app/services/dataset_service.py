from collections.abc import Sequence
from sqlmodel import Session, select

from app.models.dataset import Dataset, DatasetCreate, DatasetUpdate
from app.services.base_service import BaseService
from app.services.shot_service import ShotService


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

    def create(self, obj_in: DatasetCreate) -> Dataset:
        # Ensure the shot exists before creating the dataset
        shot_service = ShotService(self.session)
        if not shot_service.get(obj_in.shot_id):
            raise ValueError(f"Shot with id {obj_in.shot_id} not found")
        # Call the base class's create method
        return super().create(obj_in)

    def get_datasets_for_shot(
        self, shot_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Dataset]:
        statement = (
            select(Dataset).where(Dataset.shot_id == shot_id).offset(offset).limit(limit)
        )
        return self.session.exec(statement).all()
