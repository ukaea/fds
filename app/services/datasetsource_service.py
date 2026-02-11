from collections.abc import Sequence

from sqlmodel import Session, select

from app.auth.permissions import check_device_admin, check_is_admin
from app.models.datasetsource import DatasetSource, DatasetSourceLink
from app.models.identity import AuthenticatedUser
from app.services.dataset_service import DatasetService
from app.services.exceptions import ResourceNotFoundError


class DatasetSourceService:
    def __init__(self, session: Session):
        self.session = session

    def get(self, *, dataset_id: int, source_id: int) -> DatasetSource | None:
        """
        Get a single dataset-source link by its composite primary key.
        """
        statement = select(DatasetSource).where(
            DatasetSource.dataset_id == dataset_id,
            DatasetSource.source_id == source_id,
        )
        return self.session.exec(statement).first()

    def create(
        self, obj_in: DatasetSourceLink, user: AuthenticatedUser
    ) -> DatasetSource:
        """
        Create a new provenance record (DatasetSource link).
        Requires authorisation for the associated dataset.
        """
        # 1. Validate Dataset & Auth
        dataset_service = DatasetService(self.session)
        dataset = dataset_service.get(obj_in.dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {obj_in.dataset_id} not found")

        if dataset.device_name:
            check_device_admin(user, dataset.device_name)
        else:
            check_is_admin(user)

        # 2. Validate Source
        from app.services.source_service import SourceService

        if not SourceService(self.session).get(obj_in.source_id):
            raise ResourceNotFoundError(f"Source {obj_in.source_id} not found")

        # 3. Create
        db_obj = DatasetSource.model_validate(obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete_with_auth(
        self, *, dataset_id: int, source_id: int, user: AuthenticatedUser
    ) -> bool:
        """
        Delete a provenance record with authorisation.
        """
        db_obj = self.get(dataset_id=dataset_id, source_id=source_id)
        if not db_obj:
            raise ResourceNotFoundError("Provenance record not found")

        # Auth: Use associated dataset's context
        dataset_service = DatasetService(self.session)
        dataset = dataset_service.get(dataset_id)
        # Auth check
        if dataset and dataset.device_name:
            check_device_admin(user, dataset.device_name)
        else:
            check_is_admin(user)

        self.session.delete(db_obj)
        self.session.commit()
        return True

    def get_for_dataset(
        self, *, dataset_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[DatasetSource]:
        """
        Get all source links for a given dataset.
        """
        statement = (
            select(DatasetSource)
            .where(DatasetSource.dataset_id == dataset_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_for_source(
        self, *, source_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[DatasetSource]:
        """
        Get all dataset links for a given source.
        """
        statement = (
            select(DatasetSource)
            .where(DatasetSource.source_id == source_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
