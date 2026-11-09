from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    DEFAULT_PAGE_SIZE,
    BaseURLDep,
    CollectionServiceDep,
    CurrentUserDep,
    DatasetServiceDep,
    Limit,
    Offset,
    WantsJSONLDDep,
)
from app.api.negotiation import (
    JSONLD_ALTERNATIVE,
    VARY_ACCEPT,
    JSONLDResponse,
)
from app.models.activity import ActivityRead, ActivityType
from app.models.available_properties import AvailableProperties
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
from app.models.scope import CatalogueScope, DeviceScope
from app.services.available_properties import DEFAULT_MAX_VALUES
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
    responses=JSONLD_ALTERNATIVE,
)
def read_collections_global(
    *,
    jsonld: WantsJSONLDDep,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    scope: CatalogueScope = CatalogueScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
    include_replaced: bool = False,
    shot_id_prefix: str | None = None,
    base: BaseURLDep,
) -> list[CollectionRead] | JSONLDResponse:
    """Retrieve every Collection accessible to the current user.

    A collection is attached to a shot, to a device as a whole, or to neither,
    in which case it is global. All of them are listed unless `scope` asks for
    one kind: `global`, `device` or `shot`.

    `name` keeps the collections with that name, so
    `?scope=global&name=jintrac-42` finds a global collection by name. A name
    that matches nothing gives an empty page.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. A property inside a group is named by its path, the
    names joined by `.`: `nbi.beam.source:SW`. Repeat it with a *different* name
    to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.

    `activity_type`, `source` and `activity_id` filter on the Activity each
    collection bundles, the one its `activity_id` names:
    `?activity_type=simulation` lists the bundles of simulations. A bundle can
    also hold datasets its Activity did not generate, such as the Activity's
    inputs. To list only what an Activity generated, filter the dataset listings
    on `activity_id`.

    A collection is left out when you may read a collection that replaces
    it, unless `include_replaced=true`.

    `shot_id_prefix` keeps the collections on a shot whose ID starts with it, so
    `304` finds those on shots 30420 and 30421. A collection on no shot never
    matches.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each collection's `dcat:Catalog` node, in listing order.
    """
    collections = collection_service.get_multi(
        user=user,
        scope=scope,
        offset=offset,
        limit=limit,
        name=name,
        properties=properties,
        activity_type=activity_type,
        source=source,
        activity_id=activity_id,
        include_replaced=include_replaced,
        shot_id_prefix=shot_id_prefix,
    )
    if jsonld:
        document = collection_service.to_dcat_listing(collections, base, user)
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return collection_service.to_read_models(collections, include_storage_options, user)


@router.get(
    "/collections/properties",
    response_model=AvailableProperties,
    response_model_exclude_none=True,
)
def read_collection_properties(
    *,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    scope: CatalogueScope = CatalogueScope.ALL,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
    include_replaced: bool = False,
    shot_id_prefix: str | None = None,
    max_values: int = DEFAULT_MAX_VALUES,
    include_constant: bool = False,
) -> AvailableProperties:
    """
    The properties the listed collections carry, for building a filter.

    One entry per property, named by its path, with how many collections carry
    it, how many distinct values it has, and the values themselves when there
    are at most `max_values` of them. A group is not an entry: each property
    inside it is, as `nbi.beam.source`. Takes the same filters as `/collections`,
    so `total` is the number of matching collections: with
    `?activity_type=simulation` it summarises what simulation runs were about.

    When a filter names a property inside a group, the summary describes only
    the group entries that match it. Say a collection records two neutral beams,
    SS at 1.6 MW and SW at 1.4 MW. Filtered by `property=nbi.beam.source:SW`,
    the summary gives `nbi.beam.power` as 1.4, the SW beam's power, rather
    than 1.4 to 1.6.

    A property is normally left out when every collection in scope has the same
    single value for it, because picking that value would not narrow anything.
    `include_constant=true` lists it anyway. A filter panel uses this to see
    which options are still possible once something has been picked.
    """
    return collection_service.available_properties(
        user=user,
        scope=scope,
        name=name,
        properties=properties,
        activity_type=activity_type,
        source=source,
        activity_id=activity_id,
        include_replaced=include_replaced,
        shot_id_prefix=shot_id_prefix,
        max_values=max_values,
        include_constant=include_constant,
    )


@router.get(
    "/collections/{id:int}",
    response_model=CollectionRead,
    response_model_exclude_none=True,
    responses=JSONLD_ALTERNATIVE,
)
def read_collection(
    *,
    jsonld: WantsJSONLDDep,
    id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    include_storage_options: bool = False,
    base: BaseURLDep,
) -> CollectionRead | JSONLDResponse:
    """Retrieve a single Collection by its ID.

    To find a collection by name, filter a listing:
    `GET /collections?scope=global&name=jintrac-42`.

    Supports content negotiation:
    - ``Accept: application/ld+json`` → returns a ``dcat:Catalog`` JSON-LD document.
    """
    collection = collection_service.get(id)
    if not collection:
        raise ResourceNotFoundError(f"Collection {id} not found")
    collection_service.check_read_access(collection, user)

    if jsonld:
        dcat_metadata = collection_service.to_dcat(collection, base, user)
        return JSONLDResponse(content=dcat_metadata, headers=VARY_ACCEPT)
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
    responses=JSONLD_ALTERNATIVE,
)
def read_collections_device(
    *,
    jsonld: WantsJSONLDDep,
    device_name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    scope: DeviceScope = DeviceScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
    include_replaced: bool = False,
    shot_id_prefix: str | None = None,
    base: BaseURLDep,
) -> list[CollectionRead] | JSONLDResponse:
    """Retrieve a device's Collections that the current user may read.

    These are the collections attached to the device as a whole and those
    attached to its shots. `scope=device` lists only the first, `scope=shot`
    only the second.

    `name` keeps the collections with that name, so `?scope=device&name=coils`
    finds a device-level collection by name.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. A property inside a group is named by its path, the
    names joined by `.`: `nbi.beam.source:SW`. Repeat it with a *different* name
    to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.

    `activity_type`, `source` and `activity_id` filter on the Activity each
    collection bundles, the one its `activity_id` names:
    `?activity_type=simulation` lists the bundles of simulations. A bundle can
    also hold datasets its Activity did not generate, such as the Activity's
    inputs. To list only what an Activity generated, filter the dataset listings
    on `activity_id`.

    A collection is left out when you may read a collection that replaces
    it, unless `include_replaced=true`.

    `shot_id_prefix` keeps the collections on a shot whose ID starts with it, so
    `304` finds those on shots 30420 and 30421. A collection on no shot never
    matches.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each collection's `dcat:Catalog` node, in listing order.
    """
    collections = collection_service.get_collections_for_device(
        device_name,
        user=user,
        scope=scope,
        offset=offset,
        limit=limit,
        name=name,
        properties=properties,
        activity_type=activity_type,
        source=source,
        activity_id=activity_id,
        include_replaced=include_replaced,
        shot_id_prefix=shot_id_prefix,
    )
    if jsonld:
        document = collection_service.to_dcat_listing(collections, base, user)
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return collection_service.to_read_models(collections, include_storage_options, user)


@router.get(
    "/devices/{device_name}/collections/properties",
    response_model=AvailableProperties,
    response_model_exclude_none=True,
)
def read_collection_properties_device(
    *,
    device_name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    scope: DeviceScope = DeviceScope.ALL,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
    include_replaced: bool = False,
    shot_id_prefix: str | None = None,
    max_values: int = DEFAULT_MAX_VALUES,
    include_constant: bool = False,
) -> AvailableProperties:
    """
    The properties a device's listed collections carry, for building a filter.

    One entry per property, named by its path, with how many collections carry
    it, how many distinct values it has, and the values themselves when there
    are at most `max_values` of them. A group is not an entry: each property
    inside it is, as `nbi.beam.source`. Takes the same filters as
    `/devices/{device_name}/collections`, so `total` is the number of matching
    collections.

    When a filter names a property inside a group, the summary describes only
    the group entries that match it. Say a collection records two neutral beams,
    SS at 1.6 MW and SW at 1.4 MW. Filtered by `property=nbi.beam.source:SW`,
    the summary gives `nbi.beam.power` as 1.4, the SW beam's power, rather
    than 1.4 to 1.6.

    A property is normally left out when every collection in scope has the same
    single value for it, because picking that value would not narrow anything.
    `include_constant=true` lists it anyway. A filter panel uses this to see
    which options are still possible once something has been picked.
    """
    return collection_service.available_properties(
        user=user,
        device_name=device_name,
        scope=scope,
        name=name,
        properties=properties,
        activity_type=activity_type,
        source=source,
        activity_id=activity_id,
        include_replaced=include_replaced,
        shot_id_prefix=shot_id_prefix,
        max_values=max_values,
        include_constant=include_constant,
    )


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
    responses=JSONLD_ALTERNATIVE,
)
def read_collections_shot(
    *,
    jsonld: WantsJSONLDDep,
    device_name: str,
    shot_id: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_storage_options: bool = False,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
    include_replaced: bool = False,
    base: BaseURLDep,
) -> list[CollectionRead] | JSONLDResponse:
    """Retrieve all Collections scoped to a specific shot.

    `name` keeps the collection with that name. Names are unique on a shot, so
    the page holds one collection, or none.

    `property` filters on the Collection's own `scientific_metadata`. Use `elm`
    to match any collection that carries that property, or `elm:type-I` to match
    a particular value. A property inside a group is named by its path, the
    names joined by `.`: `nbi.beam.source:SW`. Repeat it with a *different* name
    to require both:
    `?property=disruption&property=elm` matches only collections carrying
    each.

    `activity_type`, `source` and `activity_id` filter on the Activity each
    collection bundles, the one its `activity_id` names:
    `?activity_type=simulation` lists the bundles of simulations. A bundle can
    also hold datasets its Activity did not generate, such as the Activity's
    inputs. To list only what an Activity generated, filter the dataset listings
    on `activity_id`.

    A collection is left out when you may read a collection that replaces
    it, unless `include_replaced=true`.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each collection's `dcat:Catalog` node, in listing order.
    """
    collections = collection_service.get_collections_for_shot(
        shot_id,
        device_name,
        user=user,
        offset=offset,
        limit=limit,
        name=name,
        properties=properties,
        activity_type=activity_type,
        source=source,
        activity_id=activity_id,
        include_replaced=include_replaced,
    )
    if jsonld:
        document = collection_service.to_dcat_listing(collections, base, user)
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return collection_service.to_read_models(collections, include_storage_options, user)


@router.patch(
    "/collections/{id:int}",
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
    "/collections/{id:int}",
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
    "/collections/{collection_id:int}/datasets",
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
    "/collections/{collection_id:int}/collections",
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
    return collection_service.to_summary_read_models(children, user)


@router.post(
    "/collections/{collection_id:int}/datasets/{dataset_id:int}",
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
    "/collections/{collection_id:int}/datasets/{dataset_id:int}",
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
    "/collections/{parent_id:int}/collections/{child_id:int}",
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
    "/collections/{parent_id:int}/collections/{child_id:int}",
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
    "/collections/{collection_id:int}/activity",
    response_model=ActivityRead,
)
def read_collection_activity(
    *,
    collection_id: int,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """Retrieve the Activity that generated this Collection.

    Returns 404 if the Collection has no associated activity.
    """
    return ActivityRead.model_validate(
        collection_service.get_activity(collection_id, user)
    )
