from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    DEFAULT_PAGE_SIZE,
    ActivityServiceDep,
    BaseURLDep,
    CollectionServiceDep,
    CurrentUserDep,
    DatasetServiceDep,
    Limit,
    Offset,
)
from app.models.activity import ActivityRead
from app.models.collection import (
    CollectionCreate,
    CollectionDataset,
    CollectionDatasetRead,
    CollectionMember,
    CollectionMemberRead,
    CollectionRead,
    CollectionUpdate,
)
from app.models.dataset import DatasetRead
from app.services.exceptions import ResourceNotFoundError

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
    include_storage_options: bool = False,
) -> CollectionRead:
    """Create a global Collection (not scoped to any device or shot)."""
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection, include_storage_options, user)


@router.get(
    "/collections",
    response_model=list[CollectionRead],
    response_model_exclude_none=True,
)
def read_collections_global(
    *,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
) -> list[CollectionRead]:
    """Retrieve all global Collections accessible to the current user.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. Repeat it with a *different* name to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.
    """
    collections = collection_service.get_multi(
        user=user, offset=offset, limit=limit, properties=properties
    )
    return collection_service.to_read_models(collections, include_storage_options, user)


@router.get(
    "/collections/id/{id}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
)
def read_collection_by_id(
    *,
    request: Request,
    id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
    base: BaseURLDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a single Collection by its internal integer ID.

    This is the URI the semantic projection names a Collection by, so it has to
    resolve: a dangling identifier is worse than none.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get(id)
    if not collection:
        raise ResourceNotFoundError(f"Collection {id} not found")
    collection_service.check_read_access(collection, user)

    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = collection_service.to_dcat(collection, base, user)
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection, include_storage_options, user)


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
    include_storage_options: bool = False,
    base: BaseURLDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific global Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = collection_service.to_dcat(collection, base, user)
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection, include_storage_options, user)


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
    include_storage_options: bool = False,
) -> CollectionRead:
    """Create a device-level Collection (not tied to any shot)."""
    collection_in.device_name = device_name
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection, include_storage_options, user)


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
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
) -> list[CollectionRead]:
    """Retrieve all device-level Collections accessible to the current user.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. Repeat it with a *different* name to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.
    """
    collections = collection_service.get_collections_for_device(
        device_name, user=user, offset=offset, limit=limit, properties=properties
    )
    return collection_service.to_read_models(collections, include_storage_options, user)


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
    include_storage_options: bool = False,
    base: BaseURLDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific device-level Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user, device_name=device_name
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = collection_service.to_dcat(collection, base, user)
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection, include_storage_options, user)


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
    include_storage_options: bool = False,
) -> CollectionRead:
    """Create a Collection scoped to a specific shot."""
    collection_in.device_name = device_name
    collection_in.shot_id = shot_id
    collection = collection_service.create(collection_in, user)
    return collection_service.to_read_model(collection, include_storage_options, user)


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
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
) -> list[CollectionRead]:
    """Retrieve all Collections scoped to a specific shot.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. Repeat it with a *different* name to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.
    """
    collections = collection_service.get_collections_for_shot(
        shot_id,
        device_name,
        user=user,
        offset=offset,
        limit=limit,
        properties=properties,
    )
    return collection_service.to_read_models(collections, include_storage_options, user)


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
    include_storage_options: bool = False,
    base: BaseURLDep,
) -> CollectionRead | JSONResponse:
    """Retrieve a specific shot-scoped Collection by name.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get_by_name_in_context_or_raise(
        name=name, user=user, device_name=device_name, shot_id=shot_id
    )
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = collection_service.to_dcat(collection, base, user)
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")
    return collection_service.to_read_model(collection, include_storage_options, user)


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


@router.get(
    "/collections/{collection_id}/datasets",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
)
def read_collection_datasets(
    *,
    collection_id: int,
    collection_service: CollectionServiceDep,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
) -> list[DatasetRead]:
    """Page through a Collection's member Datasets, ordered by id.

    A collection read inlines only the first page; this returns the rest. A page
    shorter than `limit` is the last.
    """
    collection_service.get_readable_or_raise(collection_id, user)
    datasets = collection_service.get_member_datasets(
        collection_id, user, offset=offset, limit=limit
    )
    return dataset_service.to_read_models(
        datasets, include_storage_options=include_storage_options, user=user
    )


@router.get(
    "/collections/{collection_id}/collections",
    response_model=list[CollectionRead],
    response_model_exclude_none=True,
)
def read_child_collections(
    *,
    collection_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
) -> list[CollectionRead]:
    """Page through the Collections nested directly in a Collection, ordered by id.

    Each child is returned without its own members; read it to get those. A page
    shorter than `limit` is the last.
    """
    collection_service.get_readable_or_raise(collection_id, user)
    children = collection_service.get_child_collections(
        collection_id, user, offset=offset, limit=limit
    )
    return collection_service.to_summary_read_models(children)


@router.post(
    "/collections/{collection_id}/datasets/{dataset_id}",
    response_model=CollectionDatasetRead,
    status_code=status.HTTP_201_CREATED,
)
def add_dataset_to_collection(
    *,
    collection_id: int,
    dataset_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionDataset:
    """Add a Dataset as a member of a Collection.

    A Dataset can belong to multiple Collections simultaneously. The Dataset's
    own URI is unaffected by this operation.
    """
    return collection_service.add_dataset(collection_id, dataset_id, user)


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


@router.post(
    "/collections/{parent_id}/collections/{child_id}",
    response_model=CollectionMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_child_collection(
    *,
    parent_id: int,
    child_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> CollectionMember:
    """Nest a child Collection inside a parent Collection (``dcat:catalog``).

    Both Collections must already exist. The child's own URI is unaffected.
    """
    return collection_service.add_child_collection(parent_id, child_id, user)


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


@router.get(
    "/collections/{collection_id}/activity",
    response_model=ActivityRead,
)
def read_collection_activity(
    *,
    collection_id: int,
    activity_service: ActivityServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """Retrieve the Activity (provenance run) that produced this Collection.

    Returns 404 if the Collection has no associated activity.
    """
    return ActivityRead.model_validate(
        activity_service.get_for_collection(collection_id, user)
    )
