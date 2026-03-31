from collections.abc import Sequence

from sqlmodel import Session, select

from app.auth.permissions import check_device_admin, check_is_admin
from app.models.dataset import Dataset
from app.models.distribution import Distribution, DistributionCreate, DistributionUpdate
from app.models.identity import AuthenticatedUser
from app.services.base_service import BaseService
from app.services.exceptions import ConflictError, ResourceNotFoundError


class DistributionService(
    BaseService[Distribution, DistributionCreate, DistributionUpdate]
):
    def __init__(self, session: Session):
        super().__init__(model=Distribution, session=session)

    def get_for_dataset(self, dataset_id: int) -> Sequence[Distribution]:
        statement = select(Distribution).where(Distribution.dataset_id == dataset_id)
        return self.session.exec(statement).all()

    def create(
        self, dataset_id: int, obj_in: DistributionCreate, user: AuthenticatedUser
    ) -> Distribution:
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")

        self._check_write_access(dataset, user)

        # If this is being set as default, clear the existing default first
        if obj_in.default_distribution:
            self._clear_default(dataset_id)

        db_obj = Distribution(dataset_id=dataset_id, **obj_in.model_dump())
        self.session.add(db_obj)
        self.session.commit()
        self.session.refresh(db_obj)
        return db_obj

    def update(
        self, distribution_id: int, obj_in: DistributionUpdate, user: AuthenticatedUser
    ) -> Distribution:
        db_obj = self.get(distribution_id)
        if not db_obj:
            raise ResourceNotFoundError(f"Distribution {distribution_id} not found")

        dataset = self.session.get(Dataset, db_obj.dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {db_obj.dataset_id} not found")

        self._check_write_access(dataset, user)

        # If promoting this distribution to default, demote the current default first
        if obj_in.default_distribution and db_obj.dataset_id is not None:
            self._clear_default(db_obj.dataset_id)

        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, distribution_id: int, user: AuthenticatedUser) -> bool:
        db_obj = self.get(distribution_id)
        if not db_obj:
            raise ResourceNotFoundError(f"Distribution {distribution_id} not found")

        dataset = self.session.get(Dataset, db_obj.dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {db_obj.dataset_id} not found")

        self._check_write_access(dataset, user)

        if db_obj.default_distribution:
            raise ConflictError(
                "Cannot delete the default distribution. "
                "Set another distribution as default first."
            )

        return self.delete_unchecked(distribution_id)

    def _clear_default(self, dataset_id: int) -> None:
        """Demote all current default distributions for a dataset.

        Called before promoting a new default to ensure at most one distribution
        carries ``default_distribution=True`` at any time.
        """
        statement = select(Distribution).where(
            Distribution.dataset_id == dataset_id,
            Distribution.default_distribution == True,  # noqa: E712
        )
        for dist in self.session.exec(statement).all():
            dist.default_distribution = False
            self.session.add(dist)

    def _check_write_access(self, dataset: Dataset, user: AuthenticatedUser) -> None:
        if dataset.device_name:
            check_device_admin(user, dataset.device_name)
        else:
            check_is_admin(user)
