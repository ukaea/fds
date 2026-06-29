from collections.abc import Iterable

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    ActivityServiceDep,
    BoundedLimit,
    CurrentUserDep,
    DatasetServiceDep,
    DistributionServiceDep,
    SourceServiceDep,
)
from app.models.activity import ActivityRead
from app.models.dataset import DatasetCreate, DatasetRead, DatasetUpdate
from app.models.distribution import (
    DistributionCreate,
    DistributionRead,
    DistributionUpdate,
)
from app.models.source import SourceRead
from app.services.exceptions import ResourceNotFoundError
from app.services.jsonld import map_dataset_to_dcat

router = APIRouter()


@router.post(
    "/datasets",
    response_model=DatasetRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset_global(
    *,
    dataset_service: DatasetServiceDep,
    dataset_in: DatasetCreate,
    user: CurrentUserDep,
) -> DatasetRead:
    """
    Create a global dataset.
    """
    dataset = dataset_service.create(dataset_in, user)
    return dataset_service.to_read_model(dataset)


@router.get(
    "/datasets",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_datasets_global(
    *,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: BoundedLimit = 100,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve global datasets.
    """
    datasets = dataset_service.get_multi(user=user, offset=offset, limit=limit)
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/datasets/export",
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": (
                "NDJSON stream of DatasetRead records, one per line. "
                "Optional `device_name` and `shot_id` query parameters narrow "
                "the scope to mirror the path-based list endpoints."
            ),
        }
    },
)
def export_datasets(
    *,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    device_name: str | None = None,
    shot_id: str | None = None,
) -> Iterable[DatasetRead]:
    """Stream every Dataset the caller can read as NDJSON (ADR-0020).

    Auth posture mirrors the corresponding list endpoint: open to anonymous
    callers; per-row access filtering silently drops records the caller
    cannot see. An empty result set returns 200 with an empty body.
    """
    rows = (
        dataset_service.to_read_model(d)
        for d in dataset_service.stream(
            user=user, device_name=device_name, shot_id=shot_id
        )
    )
    for row in rows:
        yield row


@router.post(
    "/devices/{device_name}/datasets",
    response_model=DatasetRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset_device(
    *,
    device_name: str,
    dataset_service: DatasetServiceDep,
    dataset_in: DatasetCreate,
    user: CurrentUserDep,
) -> DatasetRead:
    """
    Create a dataset for a specific device context.
    """
    dataset_in.device_name = device_name
    dataset = dataset_service.create(dataset_in, user)
    return dataset_service.to_read_model(dataset)


@router.post(
    "/devices/{device_name}/shots/{shot_id}/datasets",
    response_model=DatasetRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_dataset_shot(
    *,
    device_name: str,
    shot_id: str,
    dataset_service: DatasetServiceDep,
    dataset_in: DatasetCreate,
    user: CurrentUserDep,
) -> DatasetRead:
    """
    Create a dataset for a specific shot context.
    """
    dataset_in.device_name = device_name
    dataset_in.shot_id = shot_id
    dataset = dataset_service.create(dataset_in, user)
    return dataset_service.to_read_model(dataset)


@router.get(
    "/devices/{device_name}/shots/{shot_id}/datasets",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_datasets_shot(
    *,
    device_name: str,
    shot_id: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: BoundedLimit = 100,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve all datasets for a specific shot.
    """
    datasets = dataset_service.get_datasets_for_shot(
        shot_id, device_name, user=user, offset=offset, limit=limit
    )
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/devices/{device_name}/shots/{shot_id}/datasets/{name}",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_dataset_by_name(
    *,
    device_name: str,
    shot_id: str,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve all datasets with the given name within a shot context.
    Multiple datasets may share a name when produced by different Activities.
    """
    datasets = dataset_service.get_by_name_in_context(
        name=name, user=user, device_name=device_name, shot_id=shot_id
    )
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/datasets/id/{id}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
)
def read_dataset_by_id(
    *,
    request: Request,
    id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
) -> DatasetRead | JSONResponse:
    """
    Retrieve a single dataset by its internal integer ID.
    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    dataset = dataset_service.get(id)
    if not dataset:
        raise ResourceNotFoundError(f"Dataset {id} not found")
    dataset_service.check_read_access(dataset, user)

    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_dataset_to_dcat(dataset, str(request.base_url).rstrip("/"))
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")

    return dataset_service.to_read_model(
        dataset, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/datasets/{name}",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_dataset_global_by_name(
    *,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve all global datasets with the given name.
    """
    datasets = dataset_service.get_by_name_in_context(name=name, user=user)
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/devices/{device_name}/datasets",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_datasets_device(
    *,
    device_name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: BoundedLimit = 100,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve datasets for a specific device (not tied to any shot).
    """
    datasets = dataset_service.get_device_level_datasets(
        device_name, user=user, offset=offset, limit=limit
    )
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/devices/{device_name}/datasets/{name}",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_dataset_device_by_name(
    *,
    device_name: str,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """
    Retrieve all device-level datasets with the given name.
    """
    datasets = dataset_service.get_by_name_in_context(
        name=name, user=user, device_name=device_name
    )
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.patch(
    "/datasets/{id}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
)
def update_dataset(
    *,
    id: int,
    dataset_in: DatasetUpdate,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetRead:
    """
    Update a dataset. Requires appropriate tiered authorization.
    """
    dataset = dataset_service.update(id=id, obj_in=dataset_in, user=user)
    return dataset_service.to_read_model(dataset)


@router.delete(
    "/datasets/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(
    *,
    id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete a dataset by internal ID. Requires appropriate tiered authorization.
    """
    dataset_service.delete(id, user)
    return None


@router.post(
    "/datasets/{dataset_id}/distributions",
    response_model=DistributionRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_distribution(
    *,
    dataset_id: int,
    distribution_in: DistributionCreate,
    distribution_service: DistributionServiceDep,
    user: CurrentUserDep,
) -> DistributionRead:
    """
    Add a distribution to a dataset.
    """
    return DistributionRead.model_validate(
        distribution_service.create(dataset_id, distribution_in, user)
    )


@router.get(
    "/datasets/{dataset_id}/distributions",
    response_model=list[DistributionRead],
    response_model_exclude_none=True,
)
def read_distributions(
    *,
    dataset_id: int,
    distribution_service: DistributionServiceDep,
) -> list[DistributionRead]:
    """
    List all distributions for a dataset.
    """
    return [
        DistributionRead.model_validate(d)
        for d in distribution_service.get_for_dataset(dataset_id)
    ]


@router.patch(
    "/distributions/{distribution_id}",
    response_model=DistributionRead,
    response_model_exclude_none=True,
)
def update_distribution(
    *,
    distribution_id: int,
    distribution_in: DistributionUpdate,
    distribution_service: DistributionServiceDep,
    user: CurrentUserDep,
) -> DistributionRead:
    """
    Update a distribution. Setting default_distribution=true promotes this
    distribution to default and demotes the previous default.
    """
    return DistributionRead.model_validate(
        distribution_service.update(distribution_id, distribution_in, user)
    )


@router.delete(
    "/distributions/{distribution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_distribution(
    *,
    distribution_id: int,
    distribution_service: DistributionServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete a distribution. The default distribution cannot be deleted.
    """
    distribution_service.delete(distribution_id, user)
    return None


@router.get(
    "/datasets/{dataset_id}/activity",
    response_model=ActivityRead,
)
def read_dataset_activity(
    *,
    dataset_id: int,
    activity_service: ActivityServiceDep,
) -> ActivityRead:
    """
    Retrieve the Activity (provenance run) that produced this dataset,
    including timestamps, parameters, and source version.
    Returns 404 if the dataset has no associated activity.
    """
    return ActivityRead.model_validate(activity_service.get_for_dataset(dataset_id))


@router.get(
    "/datasets/{dataset_id}/source",
    response_model=SourceRead,
)
def read_dataset_source(
    *,
    dataset_id: int,
    activity_service: ActivityServiceDep,
    source_service: SourceServiceDep,
) -> SourceRead:
    """
    Retrieve the Source (diagnostic system or code) that produced this dataset.
    Shortcut for dataset → activity → source. Returns 404 if the dataset has no activity.
    """
    activity = activity_service.get_for_dataset(dataset_id)
    return source_service.to_read_model(activity.source)
