from fastapi import APIRouter
from fastapi.responses import JSONResponse

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
from app.services.exceptions import ResourceNotFoundError
from app.services.identifiers import (
    ACTIVITY,
    COLLECTION,
    DATASET,
    DEVICE,
    SHOT,
    SOURCE,
)
from app.services.jsonld import (
    map_activity_to_dcat,
    map_collection_to_dcat,
    map_device_to_dcat,
    map_shot_to_dcat,
    map_source_to_dcat,
)

router = APIRouter(tags=["identifiers"])

LD_JSON = "application/ld+json"


def _ld(document: dict) -> JSONResponse:
    return JSONResponse(content=document, media_type=LD_JSON)


@router.get(DEVICE, summary="The device this URI names")
def resolve_device(
    name: str,
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONResponse:
    device = device_service.get_by_name(name, user=user)
    return _ld(map_device_to_dcat(device, base))


@router.get(SHOT, summary="The shot this URI names")
def resolve_shot(
    name: str,
    shot_id: str,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONResponse:
    shot = shot_service.get_by_device_name(shot_id, name, user)
    return _ld(map_shot_to_dcat(shot, base))


@router.get(DATASET, summary="The dataset this URI names")
def resolve_dataset(
    id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONResponse:
    dataset = dataset_service.get(id)
    if not dataset:
        raise ResourceNotFoundError(f"Dataset {id} not found")
    dataset_service.check_read_access(dataset, user)
    return _ld(dataset_service.to_dcat(dataset, base))


@router.get(COLLECTION, summary="The collection this URI names")
def resolve_collection(
    id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> JSONResponse:
    collection = collection_service.get(id)
    if not collection:
        raise ResourceNotFoundError(f"Collection {id} not found")
    collection_service.check_read_access(collection, user)
    return _ld(map_collection_to_dcat(collection, base))


@router.get(SOURCE, summary="The source this URI names")
def resolve_source(
    id: int, source_service: SourceServiceDep, base: BaseURLDep
) -> JSONResponse:
    source = source_service.get(id)
    if not source:
        raise ResourceNotFoundError(f"Source {id} not found")
    return _ld(map_source_to_dcat(source, base))


@router.get(ACTIVITY, summary="The activity this URI names")
def resolve_activity(
    id: int, activity_service: ActivityServiceDep, base: BaseURLDep
) -> JSONResponse:
    activity = activity_service.get(id)
    if not activity:
        raise ResourceNotFoundError(f"Activity {id} not found")
    return _ld(map_activity_to_dcat(activity, base))
