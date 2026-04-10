from collections.abc import Sequence

from sqlmodel import Session, select

from app.auth.permissions import check_is_admin
from app.models.activity import Activity, ActivityCreate, ActivityInput, ActivityUpdate
from app.models.dataset import Dataset
from app.models.identity import AuthenticatedUser
from app.services.base_service import BaseService
from app.services.exceptions import ResourceNotFoundError
from app.services.source_service import SourceService


class ActivityService(BaseService[Activity, ActivityCreate, ActivityUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Activity, session=session)

    def create(self, obj_in: ActivityCreate, user: AuthenticatedUser) -> Activity:
        """
        Create a new Activity. Requires global admin.
        Validates that the referenced Source exists.
        """
        check_is_admin(user)

        if not SourceService(self.session).get(obj_in.source_id):
            raise ResourceNotFoundError(f"Source {obj_in.source_id} not found")

        return self.create_unchecked(obj_in)

    def update(
        self, *, id: int, obj_in: ActivityUpdate, user: AuthenticatedUser
    ) -> Activity:
        """
        Update an Activity. Requires global admin.
        """
        check_is_admin(user)

        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Activity {id} not found")

        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete an Activity. Requires global admin.
        """
        check_is_admin(user)

        if not self.get(id):
            raise ResourceNotFoundError(f"Activity {id} not found")

        return self.delete_unchecked(id)

    def get_for_dataset(self, dataset_id: int) -> Activity:
        """
        Retrieve the Activity that produced the given Dataset.
        Raises ResourceNotFoundError if the dataset does not exist or has no activity.
        """
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        if not dataset.activity_id:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} has no associated activity"
            )
        activity = self.get(dataset.activity_id)
        if not activity:
            raise ResourceNotFoundError(f"Activity {dataset.activity_id} not found")
        return activity

    def add_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> ActivityInput:
        """
        Mark a dataset as an input consumed by this Activity (prov:used).
        Requires global admin.
        """
        check_is_admin(user)

        if not self.get(activity_id):
            raise ResourceNotFoundError(f"Activity {activity_id} not found")
        if not self.session.get(Dataset, dataset_id):
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")

        existing = self.session.get(ActivityInput, (activity_id, dataset_id))
        if existing:
            return existing

        link = ActivityInput(activity_id=activity_id, dataset_id=dataset_id)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> bool:
        """
        Unlink an input dataset from an Activity. Requires global admin.
        """
        check_is_admin(user)

        link = self.session.get(ActivityInput, (activity_id, dataset_id))
        if not link:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} is not an input of Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_inputs(
        self, activity_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Dataset]:
        """
        List the datasets consumed as inputs by an Activity.
        """
        if not self.get(activity_id):
            raise ResourceNotFoundError(f"Activity {activity_id} not found")

        statement = (
            select(Dataset)
            .join(ActivityInput, ActivityInput.dataset_id == Dataset.id)  # type: ignore[arg-type]
            .where(ActivityInput.activity_id == activity_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_for_source(
        self, source_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Activity]:
        """
        Retrieve all Activities associated with a given Source.
        """
        statement = (
            select(Activity)
            .where(Activity.source_id == source_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
