from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.access_control import get_effective_access_level
from app.auth.permissions import check_device_admin, check_is_admin
from app.models.dataset import Dataset, DatasetCreate, DatasetRead, DatasetUpdate
from app.models.device import Device
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.base_service import BaseService
from app.services.device_service import DeviceService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.shot_service import ShotService


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

    def get_multi(
        self,
        user: AuthenticatedUser = ANONYMOUS_USER,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Global list of datasets. Filters by access level.
        """
        statement = select(self.model).offset(offset).limit(limit)
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def check_read_access(self, dataset: Dataset, user: AuthenticatedUser) -> None:
        """
        Calculates effective access level (Inheritance: Dataset > Shot > Device)
        and enforces read access.
        """
        effective_level = get_effective_access_level(dataset, self.session)

        # Public AND Embargoed metadata is accessible to everyone (Discoverable)
        if (
            effective_level == AccessLevel.PUBLIC
            or effective_level == AccessLevel.EMBARGOED
        ):
            return

        # For restricted, you must be authenticated
        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

    def create(self, obj_in: DatasetCreate, user: AuthenticatedUser) -> Dataset:
        """
        Create a new dataset. Handles global, device, or shot context.
        """
        # 1. Determine and Validate Context
        if obj_in.shot_id:
            if not obj_in.device_name:
                raise FDSValidationError(
                    "Device name is required when specifying a shot_id"
                )

            # Resolve device first
            statement = select(Device).where(Device.name == obj_in.device_name)
            device = self.session.exec(statement).first()
            if not device:
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")

            # Check Shot Context
            shot_service = ShotService(self.session)
            shot = shot_service.get(obj_in.shot_id, device.id)
            if not shot:
                raise ResourceNotFoundError(
                    f"Shot {obj_in.shot_id} not found for device {obj_in.device_name}"
                )

            # Auth: Device Admin
            check_device_admin(user, obj_in.device_name)

        elif obj_in.device_name:
            device = DeviceService(self.session).get_by_name(obj_in.device_name)
            if not device:
                raise ResourceNotFoundError(f"Device {obj_in.device_name} not found")

            # Auth: Device Admin
            check_device_admin(user, obj_in.device_name)
        else:
            # Global dataset
            check_is_admin(user)

        # 2. Check for Name Collisions
        existing = self.get_by_name_in_context(
            name=obj_in.name,
            device_name=obj_in.device_name,
            shot_id=obj_in.shot_id,
            user=user,
        )
        if existing:
            raise ConflictError(f"Dataset {obj_in.name} already exists in this context")

        # 3. Create DB Object
        db_obj = Dataset.model_validate(obj_in)

        # Populate derived fields
        if obj_in.shot_id:
            statement = select(Device).where(Device.name == obj_in.device_name)
            device = self.session.exec(statement).first()
            db_obj.device_id = device.id

        elif obj_in.device_name:
            statement = select(Device).where(Device.name == obj_in.device_name)
            device = self.session.exec(statement).first()
            db_obj.device_id = device.id

        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(
                f"Dataset '{obj_in.name}' already exists in this context"
            ) from e
        self.session.refresh(db_obj)
        return db_obj

    def update(
        self, *, db_obj: Dataset, obj_in: DatasetUpdate, user: AuthenticatedUser
    ) -> Dataset:
        """
        Update a dataset.
        """
        # Auth check based on existing context
        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        # Prevent changing context during update
        if obj_in.device_name and obj_in.device_name != db_obj.device_name:
            raise ForbiddenError("Cannot move a dataset between device contexts")
        if obj_in.shot_id and obj_in.shot_id != db_obj.shot_id:
            raise ForbiddenError("Cannot move a dataset between shots")

        return super().update(db_obj=db_obj, obj_in=obj_in)

    def delete_with_auth(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a dataset with authorization.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Dataset {id} not found")

        if db_obj.device_name:
            check_device_admin(user, db_obj.device_name)
        else:
            check_is_admin(user)

        return self.delete(id)

    def get_by_name_in_context(
        self,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        device_name: str | None = None,
        shot_id: str | None = None,
    ) -> Dataset | None:
        """
        Retrieve a dataset by name within its context, enforcing read access.
        """
        statement = select(Dataset).where(
            Dataset.name == name,
            Dataset.device_name == device_name,
            Dataset.shot_id == shot_id,
        )
        dataset = self.session.exec(statement).first()
        if dataset:
            self.check_read_access(dataset, user)
        return dataset

    def get_datasets_for_device(
        self,
        device_name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Get datasets belonging to a device (but not to a specific shot), filtering by access.
        """
        statement = (
            select(Dataset)
            .where(Dataset.device_name == device_name, Dataset.shot_id.is_(None))
            .offset(offset)
            .limit(limit)
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def get_datasets_for_shot(
        self,
        shot_id: str,
        device_id: int,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """
        Get all datasets for a specific shot (scoped by device).
        """
        statement = (
            select(Dataset)
            .where(Dataset.shot_id == shot_id, Dataset.device_id == device_id)
            .offset(offset)
            .limit(limit)
        )
        datasets = self.session.exec(statement).all()
        return self._filter_accessible_datasets(datasets, user)

    def to_read_model(self, dataset: Dataset) -> DatasetRead:
        """
        Converts a Dataset ORM object to a DatasetRead DTO, including the effective access level.
        """
        read_model = DatasetRead.model_validate(dataset)
        read_model.effective_access_level = get_effective_access_level(
            dataset, self.session
        )
        return read_model

    def _filter_accessible_datasets(
        self, datasets: Sequence[Dataset], user: AuthenticatedUser
    ) -> list[Dataset]:
        """
        Helper to filter a list of datasets, returning only those the user can read.
        """
        accessible_datasets = []
        for dataset in datasets:
            try:
                self.check_read_access(dataset, user)
                accessible_datasets.append(dataset)
            except ForbiddenError:
                continue
        return accessible_datasets
