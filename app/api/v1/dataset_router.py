from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserDep, DatasetServiceDep
from app.models.dataset import DatasetCreate, DatasetRead, DatasetUpdate
from app.services.exceptions import ResourceNotFoundError
from app.services.jsonld import map_dataset_to_dcat

router = APIRouter()


@router.post(
    "/datasets/",
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
    "/datasets/",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_datasets_global(
    *,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> list[DatasetRead]:
    """
    Retrieve global datasets.
    """
    datasets = dataset_service.get_multi(user=user, offset=offset, limit=limit)
    return [dataset_service.to_read_model(d) for d in datasets]


@router.post(
    "/devices/{device_name}/datasets/",
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
    "/devices/{device_name}/shots/{shot_id}/datasets/",
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
    "/devices/{device_name}/shots/{shot_id}/datasets/",
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
    limit: int = 100,
) -> list[DatasetRead]:
    """
    Retrieve all datasets for a specific shot.
    """
    datasets = dataset_service.get_datasets_for_shot(
        shot_id, user=user, offset=offset, limit=limit
    )
    return [dataset_service.to_read_model(d) for d in datasets]


@router.get(
    "/devices/{device_name}/shots/{shot_id}/datasets/{name}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
)
def read_dataset_by_name(
    *,
    request: Request,
    device_name: str,
    shot_id: str,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetRead | JSONResponse:
    """
    Retrieve a specific dataset by its descriptive name within a shot context.
    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    dataset = dataset_service.get_by_name_in_context(
        name=name, user=user, device_name=device_name, shot_id=shot_id
    )
    if not dataset:
        raise ResourceNotFoundError(f"Dataset {name} not found in this context")

    # Content Negotiation
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_dataset_to_dcat(dataset, str(request.base_url).rstrip("/"))
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")

    return dataset_service.to_read_model(dataset)


@router.get(
    "/datasets/{name}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
)
def read_dataset_global_by_name(
    *,
    request: Request,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetRead | JSONResponse:
    """
    Retrieve a specific global dataset by its descriptive name.
    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    dataset = dataset_service.get_by_name_in_context(name=name, user=user)
    if not dataset:
        raise ResourceNotFoundError(f"Global dataset {name} not found")

    # Content Negotiation
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_dataset_to_dcat(dataset, str(request.base_url).rstrip("/"))
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")

    return dataset_service.to_read_model(dataset)


@router.get(
    "/devices/{device_name}/datasets/",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_datasets_device(
    *,
    device_name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> list[DatasetRead]:
    """
    Retrieve datasets for a specific device (not tied to any shot).
    """
    datasets = dataset_service.get_datasets_for_device(
        device_name, user=user, offset=offset, limit=limit
    )
    return [dataset_service.to_read_model(d) for d in datasets]


@router.get(
    "/devices/{device_name}/datasets/{name}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
)
def read_dataset_device_by_name(
    *,
    request: Request,
    device_name: str,
    name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetRead | JSONResponse:
    """
    Retrieve a specific device-level dataset by its descriptive name.
    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    dataset = dataset_service.get_by_name_in_context(
        name=name, user=user, device_name=device_name
    )
    if not dataset:
        raise ResourceNotFoundError(
            f"Dataset {name} not found for device {device_name}"
        )

    # Content Negotiation
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_dataset_to_dcat(dataset, str(request.base_url).rstrip("/"))
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")

    return dataset_service.to_read_model(dataset)


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
    db_obj = dataset_service.get(id)
    if not db_obj:
        raise ResourceNotFoundError(f"Dataset {id} not found")
    dataset = dataset_service.update(db_obj=db_obj, obj_in=dataset_in, user=user)
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
    dataset_service.delete_with_auth(id, user)
    return None
