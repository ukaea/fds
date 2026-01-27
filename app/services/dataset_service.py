from collections.abc import Sequence

from sqlmodel import Session, select

from app.auth.access_control import get_effective_access_level
from app.auth.permissions import check_device_admin, check_is_admin
from app.auth.security import AuthenticatedUser
from app.models.common import AccessLevel
from app.models.dataset import Dataset, DatasetCreate, DatasetRead, DatasetUpdate
from app.models.user import ANONYMOUS_USER
from app.services.base_service import BaseService
from app.services.device_service import DeviceService
from app.services.exceptions import ConflictError, ForbiddenError, ResourceNotFoundError
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
        results = self.session.exec(statement).all()

        accessible = []
        for d in results:
            try:
                self.check_read_access(d, user)
                accessible.append(d)
            except ForbiddenError:
                continue
        return accessible

    def check_read_access(self, dataset: Dataset, user: AuthenticatedUser) -> None:
        """
        Calculates effective access level (Inheritance: Dataset > Shot > Device)
        and enforces read access.
        """
        effective_level = get_effective_access_level(dataset, self.session)

        # Public is theoretically accessible to everyone
        if effective_level == AccessLevel.PUBLIC:
            return

        # For restricted+, you must be authenticated
        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

        # FUTURE: If we have EMBARGOED or specific dataset-level scopes, add checks here.
        # For now, being authenticated is enough to see RESTRICTED (assuming scopes
        # like 'read' aren't granularly enforced per dataset yet, only device level for writes).

    def create(self, obj_in: DatasetCreate, user: AuthenticatedUser) -> Dataset:
        """
        Create a new dataset. Handles global, device, or shot context.
        """
        # 1. Determine and Validate Context
        if obj_in.shot_id:
            shot = ShotService(self.session).get(obj_in.shot_id)
            if not shot:
                raise ResourceNotFoundError(f"Shot {obj_in.shot_id} not found")

            # If device_name is also provided, ensure it matches the shot's device
            if obj_in.device_name and shot.device.name != obj_in.device_name:
                raise ConflictError(
                    f"Shot {obj_in.shot_id} does not belong to device {obj_in.device_name}"
                )

            # Use shot's device_name if not provided
            if not obj_in.device_name:
                obj_in.device_name = shot.device.name

            # Auth: Device Admin or Global Admin
            check_device_admin(user, obj_in.device_name)
        elif obj_in.device_name:
            device = DeviceService(self.session).get_by_name(obj_in.device_name)
            if not device:
                raise ResourceNotFoundError(f"Device {obj_in.device_name} not found")

            # Auth: Device Admin or Global Admin
            check_device_admin(user, obj_in.device_name)
        else:
            # Global dataset
            # Auth: Global Admin only
            check_is_admin(user)

        # 2. Check for Name Collisions (within context)
        existing = self.get_by_name_in_context(
            obj_in.name, obj_in.device_name, obj_in.shot_id
        )
        if existing:
            raise ConflictError(f"Dataset {obj_in.name} already exists in this context")

        # Call the base class's create method
        return super().create(obj_in)

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
        results = self.session.exec(statement).all()

        # Filter datasets that the user does not have access to
        accessible = []
        for d in results:
            try:
                self.check_read_access(d, user)
                accessible.append(d)
            except ForbiddenError:
                continue
        return accessible

    def get_datasets_for_shot(
        self,
        shot_id: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        statement = (
            select(Dataset)
            .where(Dataset.shot_id == shot_id)
            .offset(offset)
            .limit(limit)
        )
        results = self.session.exec(statement).all()

        # Filter datasets that the user does not have access to
        accessible = []
        for d in results:
            try:
                self.check_read_access(d, user)
                accessible.append(d)
            except ForbiddenError:
                continue
        return accessible

    def to_read_model(self, dataset: Dataset) -> DatasetRead:
        """
        Converts a Dataset ORM object to a DatasetRead DTO, including the effective access level.
        """
        read_model = DatasetRead.model_validate(dataset)
        read_model.effective_access_level = get_effective_access_level(
            dataset, self.session
        )
        return read_model
