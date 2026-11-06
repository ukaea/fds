from fastapi import APIRouter

from app.api.deps import (
    ActivityServiceDep,
    BaseURLDep,
    CollectionServiceDep,
    CurrentUserDep,
    DatasetServiceDep,
    DeviceServiceDep,
    ShotServiceDep,
    SourceServiceDep,
)
from app.api.negotiation import JSONLDResponse
from app.services.exceptions import ResourceNotFoundError
from app.services.identifiers import (
    ACTIVITY,
    CATALOG,
    COLLECTION,
    DATASET,
    DEVICE,
    SHOT,
    SOURCE,
)
from app.services.jsonld import (
    map_catalog_to_dcat,
    map_device_to_dcat,
    map_shot_to_dcat,
    map_source_to_dcat,
)

# Every route here answers in JSON-LD, whatever the Accept header asks for.
router = APIRouter(tags=["identifiers"], default_response_class=JSONLDResponse)


@router.get(DEVICE, summary="The device this URI names")
def resolve_device(
    name: str,
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    device = device_service.get_by_name(name, user=user)
    return JSONLDResponse(map_device_to_dcat(device, base))


@router.get(SHOT, summary="The shot this URI names")
def resolve_shot(
    name: str,
    shot_id: str,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    shot = shot_service.get_by_device_name(shot_id, name, user)
    return JSONLDResponse(map_shot_to_dcat(shot, base))


@router.get(DATASET, summary="The dataset this URI names")
def resolve_dataset(
    id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    dataset = dataset_service.get(id)
    if not dataset:
        raise ResourceNotFoundError(f"Dataset {id} not found")
    dataset_service.check_read_access(dataset, user)
    return JSONLDResponse(dataset_service.to_dcat(dataset, base))


@router.get(COLLECTION, summary="The collection this URI names")
def resolve_collection(
    id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    collection = collection_service.get(id)
    if not collection:
        raise ResourceNotFoundError(f"Collection {id} not found")
    collection_service.check_read_access(collection, user)
    return JSONLDResponse(collection_service.to_dcat(collection, base, user))


@router.get(SOURCE, summary="The source this URI names")
def resolve_source(
    id: int, source_service: SourceServiceDep, base: BaseURLDep
) -> JSONLDResponse:
    source = source_service.get(id)
    if not source:
        raise ResourceNotFoundError(f"Source {id} not found")
    return JSONLDResponse(map_source_to_dcat(source, base))


@router.get(ACTIVITY, summary="The activity this URI names")
def resolve_activity(
    id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    activity = activity_service.get_readable_or_raise(id, user)
    return JSONLDResponse(activity_service.to_dcat(activity, base, user))


@router.get(CATALOG, summary="The catalogue of everything this FDS holds")
def resolve_catalog(
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONLDResponse:
    return JSONLDResponse(
        map_catalog_to_dcat(device_service.get_multi(user=user), base)
    )
