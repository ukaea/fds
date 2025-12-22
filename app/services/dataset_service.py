from collections.abc import Sequence
from sqlmodel import Session, select

from app.auth.security import AuthenticatedUser
from app.auth.permissions import check_is_admin, check_device_admin
from app.models.dataset import Dataset, DatasetCreate, DatasetUpdate
from app.services.base_service import BaseService
from app.services.shot_service import ShotService
from app.services.device_service import DeviceService
from app.services.exceptions import ResourceNotFoundError, ForbiddenError, ConflictError


class DatasetService(BaseService[Dataset, DatasetCreate, DatasetUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Dataset, session=session)

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
        self, name: str, device_name: str | None = None, shot_id: str | None = None
    ) -> Dataset | None:
        """
        Retrieve a dataset by name within its context.
        """
        statement = select(Dataset).where(
            Dataset.name == name,
            Dataset.device_name == device_name,
            Dataset.shot_id == shot_id,
        )
        return self.session.exec(statement).first()

    def get_datasets_for_device(
        self, device_name: str, offset: int = 0, limit: int = 100
    ) -> Sequence[Dataset]:
        """
        Get datasets belonging to a device but not to a specific shot.
        """
        statement = (
            select(Dataset)
            .where(Dataset.device_name == device_name, Dataset.shot_id.is_(None))
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_datasets_for_shot(
        self, shot_id: str, offset: int = 0, limit: int = 100
    ) -> Sequence[Dataset]:
        statement = (
            select(Dataset)
            .where(Dataset.shot_id == shot_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
