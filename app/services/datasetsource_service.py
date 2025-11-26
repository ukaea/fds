from collections.abc import Sequence

from sqlmodel import Session, select

from app.models.datasetsource import DatasetSource, DatasetSourceCreate


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

    def create(self, obj_in: DatasetSourceCreate) -> DatasetSource:
        """
        Create a new dataset-source link.
        """
        db_obj = DatasetSource.model_validate(obj_in)
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def delete(self, *, dataset_id: int, source_id: int) -> bool:
        """
        Delete a dataset-source link by its composite primary key.
        """
        db_obj = self.get(dataset_id=dataset_id, source_id=source_id)
        if not db_obj:
            return False
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
