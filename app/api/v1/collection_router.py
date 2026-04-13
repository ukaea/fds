from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    ActivityServiceDep,
    CollectionServiceDep,
    CurrentUserDep,
)
from app.models.activity import ActivityRead
from app.models.collection import CollectionCreate, CollectionRead, CollectionUpdate
from app.services.exceptions import ResourceNotFoundError
from app.services.jsonld import map_collection_to_dcat

router = APIRouter()


@router.post(
    "/collections",
    response_model=CollectionRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_collection_global(
    *,
    collection_service: CollectionServiceDep,
    collection_in: CollectionCreate,
    user: CurrentUserDep,
) -> CollectionRead:
    """Create a global Collection (not scoped to any device or shot)."""
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection)


@router.get(
    "/collections",
    response_model=list[CollectionRead],
    response_model_exclude_none=True,
)
def read_collections_global(
    *,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> list[CollectionRead]:
    """Retrieve all global Collections accessible to the current user."""
    collections = collection_service.get_multi(user=user, offset=offset, limit=limit)
    return collection_service.to_read_models(collections)


@router.get(
    "/collections/{name}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
)
def read_collection_global_by_name(
    *,
    request: Request,
    name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific global Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_collection_to_dcat(
            collection, str(request.base_url).rstrip("/")
        )
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection)


@router.post(
    "/devices/{device_name}/collections",
    response_model=CollectionRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_collection_device(
    *,
    device_name: str,
    collection_service: CollectionServiceDep,
    collection_in: CollectionCreate,
    user: CurrentUserDep,
) -> CollectionRead:
    """Create a device-level Collection (not tied to any shot)."""
    collection_in.device_name = device_name
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection)


@router.get(
    "/devices/{device_name}/collections",
    response_model=list[CollectionRead],
    response_model_exclude_none=True,
)
def read_collections_device(
    *,
    device_name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> list[CollectionRead]:
    """Retrieve all device-level Collections accessible to the current user."""
    collections = collection_service.get_collections_for_device(
        device_name, user=user, offset=offset, limit=limit
    )
    return collection_service.to_read_models(collections)


@router.get(
    "/devices/{device_name}/collections/{name}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
)
def read_collection_device_by_name(
    *,
    request: Request,
    device_name: str,
    name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific device-level Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user, device_name=device_name
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_collection_to_dcat(
            collection, str(request.base_url).rstrip("/")
        )
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection)


@router.post(
    "/devices/{device_name}/shots/{shot_id}/collections",
    response_model=CollectionRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_collection_shot(
    *,
    device_name: str,
    shot_id: str,
    collection_service: CollectionServiceDep,
    collection_in: CollectionCreate,
    user: CurrentUserDep,
) -> CollectionRead:
    """Create a Collection scoped to a specific shot."""
    collection_in.device_name = device_name
    collection_in.shot_id = shot_id
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection)


@router.get(
    "/devices/{device_name}/shots/{shot_id}/collections",
    response_model=list[CollectionRead],
    response_model_exclude_none=True,
)
def read_collections_shot(
    *,
    device_name: str,
    shot_id: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> list[CollectionRead]:
    """Retrieve all Collections scoped to a specific shot."""
    collections = collection_service.get_collections_for_shot(
        shot_id, device_name, user=user, offset=offset, limit=limit
    )
    return collection_service.to_read_models(collections)


@router.get(
    "/devices/{device_name}/shots/{shot_id}/collections/{name}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
)
def read_collection_shot_by_name(
    *,
    request: Request,
    device_name: str,
    shot_id: str,
    name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific shot-scoped Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user, device_name=device_name, shot_id=shot_id
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_collection_to_dcat(
            collection, str(request.base_url).rstrip("/")
        )
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection)


@router.patch(
    "/collections/{id}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
)
def update_collection(
    *,
    id: int,
    collection_in: CollectionUpdate,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionRead:
    """Partially update a Collection. Requires appropriate tiered authorisation."""
    collection = collection_service.update(id=id, obj_in=collection_in, user=user)
    return collection_service.to_read_model(collection)


@router.delete(
    "/collections/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_collection(
    *,
    id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> None:
    """Delete a Collection by internal ID. Requires appropriate tiered authorisation."""
    collection_service.delete(id, user)
    return None


@router.post(
    "/collections/{collection_id}/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def add_dataset_to_collection(
    *,
    collection_id: int,
    dataset_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> None:
    """Add a Dataset as a member of a Collection.

    A Dataset can belong to multiple Collections simultaneously. The Dataset's
    own URI is unaffected by this operation.
    """
    collection_service.add_dataset(collection_id, dataset_id, user)
    return None


@router.delete(
    "/collections/{collection_id}/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_dataset_from_collection(
    *,
    collection_id: int,
    dataset_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> None:
    """Remove a Dataset from a Collection.

    Only the membership record is removed; the Dataset itself is not deleted.
    """
    collection_service.remove_dataset(collection_id, dataset_id, user)
    return None


@router.post(
    "/collections/{parent_id}/collections/{child_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def add_child_collection(
    *,
    parent_id: int,
    child_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> None:
    """Nest a child Collection inside a parent Collection (``dcat:catalog``).

    Both Collections must already exist. The child's own URI is unaffected.
    """
    collection_service.add_child_collection(parent_id, child_id, user)
    return None


@router.delete(
    "/collections/{parent_id}/collections/{child_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_child_collection(
    *,
    parent_id: int,
    child_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> None:
    """Remove a child Collection from a parent Collection.

    Only the nesting relationship is removed; neither Collection is deleted.
    """
    collection_service.remove_child_collection(parent_id, child_id, user)
    return None


@router.get(
    "/collections/{collection_id}/activity",
    response_model=ActivityRead,
)
def read_collection_activity(
    *,
    collection_id: int,
    collection_service: CollectionServiceDep,
    activity_service: ActivityServiceDep,
) -> ActivityRead:
    """Retrieve the Activity (provenance run) that produced this Collection.

    Returns 404 if the Collection has no associated activity.
    """
    collection = collection_service.get(collection_id)
    if not collection:
        raise ResourceNotFoundError(f"Collection {collection_id} not found")
    if not collection.activity_id:
        raise ResourceNotFoundError(
            f"Collection {collection_id} has no associated activity"
        )
    return ActivityRead.model_validate(activity_service.get(collection.activity_id))
