from fastapi import APIRouter, status

from app.api.deps import ActivityServiceDep, CurrentUserDep, DatasetServiceDep
from app.models.activity import ActivityCreate, ActivityRead, ActivityUpdate
from app.models.dataset import DatasetRead

router = APIRouter()


@router.post("/", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(
    *,
    activity_in: ActivityCreate,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """
    Create a new Activity (a specific execution of a Source). Requires global admin.
    """
    activity = activity_service.create(activity_in, user)
    return ActivityRead.model_validate(activity)


@router.get("/{activity_id}", response_model=ActivityRead)
def read_activity(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
) -> ActivityRead:
    """
    Retrieve a single Activity by ID.
    """
    from app.services.exceptions import ResourceNotFoundError

    activity = activity_service.get(activity_id)
    if not activity:
        raise ResourceNotFoundError(f"Activity {activity_id} not found")
    return ActivityRead.model_validate(activity)


@router.put("/{activity_id}", response_model=ActivityRead)
def update_activity(
    *,
    activity_id: int,
    activity_in: ActivityUpdate,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """
    Update an Activity. Requires global admin.
    """
    activity = activity_service.update(id=activity_id, obj_in=activity_in, user=user)
    return ActivityRead.model_validate(activity)


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete an Activity. Requires global admin.
    """
    activity_service.delete(activity_id, user)
    return None


@router.post(
    "/{activity_id}/inputs/{dataset_id}",
    status_code=status.HTTP_201_CREATED,
)
def add_activity_input(
    *,
    activity_id: int,
    dataset_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Mark a dataset as an input consumed by this Activity (prov:used).
    Requires global admin.
    """
    activity_service.add_input(
        activity_id=activity_id, dataset_id=dataset_id, user=user
    )
    return None


@router.get(
    "/{activity_id}/inputs",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def list_activity_inputs(
    *,
    activity_id: int,
    activity_service: ActivityServiceDep,
    dataset_service: DatasetServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> list[DatasetRead]:
    """
    List the datasets consumed as inputs by this Activity.
    """
    datasets = activity_service.get_inputs(activity_id, offset=offset, limit=limit)
    return dataset_service.to_read_models(list(datasets))


@router.delete(
    "/{activity_id}/inputs/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_activity_input(
    *,
    activity_id: int,
    dataset_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Unlink an input dataset from an Activity. Requires global admin.
    """
    activity_service.remove_input(
        activity_id=activity_id, dataset_id=dataset_id, user=user
    )
    return None
