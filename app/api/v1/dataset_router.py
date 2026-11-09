from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    DEFAULT_PAGE_SIZE,
    BaseURLDep,
    CurrentUserDep,
    DatasetServiceDep,
    DistributionServiceDep,
    Limit,
    Offset,
    SourceServiceDep,
    WantsJSONLDDep,
)
from app.api.listings import (
    DatasetIncludes,
    DatasetShotSpanFilters,
    LocalFilters,
)
from app.api.negotiation import (
    JSONLD_ALTERNATIVE,
    VARY_ACCEPT,
    JSONLDResponse,
)
from app.models.activity import ActivityRead
from app.models.dataset import (
    DatasetCreate,
    DatasetDerivationCreate,
    DatasetDerivationRead,
    DatasetLineageNode,
    DatasetRead,
    DatasetUpdate,
)
from app.models.distribution import (
    DistributionCreate,
    DistributionRead,
    DistributionUpdate,
)
from app.models.scope import CatalogueScope, DeviceScope
from app.models.source import SourceRead
from app.services.exceptions import ResourceNotFoundError

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
    responses=JSONLD_ALTERNATIVE,
)
def read_datasets_global(
    *,
    jsonld: WantsJSONLDDep,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    scope: CatalogueScope = CatalogueScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    filters: Annotated[LocalFilters, Query()],
    span: Annotated[DatasetShotSpanFilters, Query()],
    includes: Annotated[DatasetIncludes, Query()],
    base: BaseURLDep,
) -> list[DatasetRead] | JSONLDResponse:
    """
    Retrieve every dataset accessible to the current user.

    A dataset is attached to a shot, to a device as a whole, or to neither, in
    which case it is global. All of them are listed unless `scope` asks for one
    kind: `global`, `device` or `shot`. To scope to a single device, use
    `/devices/{device_name}/datasets`.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each dataset's `dcat:Dataset` node, in listing order.
    """
    datasets = dataset_service.get_multi(
        user=user,
        scope=scope,
        offset=offset,
        limit=limit,
        **filters.model_dump(),
        **span.model_dump(),
    )
    if jsonld:
        document = dataset_service.to_dcat_listing(
            datasets,
            base,
            user=user,
            include_geometry=includes.include_geometry,
            include_calibration=includes.include_calibration,
            include_annotations=includes.include_annotations,
        )
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return dataset_service.to_read_models(datasets, user=user, **includes.model_dump())


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
    responses=JSONLD_ALTERNATIVE,
)
def read_datasets_shot(
    *,
    jsonld: WantsJSONLDDep,
    device_name: str,
    shot_id: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    filters: Annotated[LocalFilters, Query()],
    includes: Annotated[DatasetIncludes, Query()],
    base: BaseURLDep,
) -> list[DatasetRead] | JSONLDResponse:
    """
    Retrieve all datasets for a specific shot.

    Several datasets can share a name when different Activities produced them,
    so `?name=equilibrium&source=efit` picks out EFIT's.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each dataset's `dcat:Dataset` node, in listing order.
    """
    datasets = dataset_service.get_datasets_for_shot(
        shot_id,
        device_name,
        user=user,
        offset=offset,
        limit=limit,
        **filters.model_dump(),
    )
    if jsonld:
        document = dataset_service.to_dcat_listing(
            datasets,
            base,
            user=user,
            include_geometry=includes.include_geometry,
            include_calibration=includes.include_calibration,
            include_annotations=includes.include_annotations,
        )
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return dataset_service.to_read_models(datasets, user=user, **includes.model_dump())


@router.get(
    "/datasets/{id:int}",
    response_model=DatasetRead,
    response_model_exclude_none=True,
    responses=JSONLD_ALTERNATIVE,
)
def read_dataset(
    *,
    jsonld: WantsJSONLDDep,
    id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    includes: Annotated[DatasetIncludes, Query()],
    base: BaseURLDep,
) -> DatasetRead | JSONLDResponse:
    """
    Retrieve a single dataset by its ID.

    To find a dataset by name, filter a listing:
    `GET /devices/mast/shots/30421/datasets?name=equilibrium`.

    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    dataset = dataset_service.get(id)
    if not dataset:
        raise ResourceNotFoundError(f"Dataset {id} not found")
    dataset_service.check_read_access(dataset, user)

    if jsonld:
        dcat_metadata = dataset_service.to_dcat(
            dataset,
            base,
            user=user,
            include_geometry=includes.include_geometry,
            include_calibration=includes.include_calibration,
            include_annotations=includes.include_annotations,
        )
        return JSONLDResponse(content=dcat_metadata, headers=VARY_ACCEPT)
    return dataset_service.to_read_model(dataset, user=user, **includes.model_dump())


@router.get(
    "/devices/{device_name}/datasets",
    response_model=list[DatasetRead],
    response_model_exclude_none=True,
    responses=JSONLD_ALTERNATIVE,
)
def read_datasets_device(
    *,
    jsonld: WantsJSONLDDep,
    device_name: str,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    scope: DeviceScope = DeviceScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    filters: Annotated[LocalFilters, Query()],
    span: Annotated[DatasetShotSpanFilters, Query()],
    includes: Annotated[DatasetIncludes, Query()],
    base: BaseURLDep,
) -> list[DatasetRead] | JSONLDResponse:
    """
    Retrieve datasets hosted by a device.

    By default this returns every dataset for the device, device-level and
    shot-level alike. Narrow it with `scope`: `device` for the datasets
    attached to no shot (e.g., reference geometry and calibration versions), `shot`
    for those belonging to the device's shots. Device-level datasets have no
    shot, so `shot_property` matches nothing under `scope=device`.

    With `Accept: application/ld+json` the page is one JSON-LD document whose
    `@graph` holds each dataset's `dcat:Dataset` node, in listing order.
    """
    datasets = dataset_service.get_datasets_for_device(
        device_name,
        user=user,
        scope=scope,
        offset=offset,
        limit=limit,
        **filters.model_dump(),
        **span.model_dump(),
    )
    if jsonld:
        document = dataset_service.to_dcat_listing(
            datasets,
            base,
            user=user,
            include_geometry=includes.include_geometry,
            include_calibration=includes.include_calibration,
            include_annotations=includes.include_annotations,
        )
        return JSONLDResponse(content=document, headers=VARY_ACCEPT)
    return dataset_service.to_read_models(datasets, user=user, **includes.model_dump())


@router.patch(
    "/datasets/{id:int}",
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
    "/datasets/{id:int}",
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


@router.post(
    "/datasets/{dataset_id:int}/derivations",
    response_model=DatasetDerivationRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_derivation(
    *,
    dataset_id: int,
    derivation_in: DatasetDerivationCreate,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetDerivationRead:
    """
    Assert an upstream entity this dataset was derived from.

    The upstream need not be registered in FDS: name it by ``source_dataset_id``
    if it is, else by ``source_identifier`` (a DOI, URL or other PID), else by
    ``source_label`` and ``source_description`` alone.
    """
    return DatasetDerivationRead.model_validate(
        dataset_service.add_derivation(
            dataset_id=dataset_id, obj_in=derivation_in, user=user
        )
    )


@router.get(
    "/datasets/{dataset_id:int}/derivations",
    response_model=list[DatasetDerivationRead],
    response_model_exclude_none=True,
)
def read_derivations(
    *,
    dataset_id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
) -> list[DatasetDerivationRead]:
    """
    List the upstream entities asserted for a dataset.
    """
    return [
        DatasetDerivationRead.model_validate(d)
        for d in dataset_service.get_derivations(
            dataset_id, user=user, offset=offset, limit=limit
        )
    ]


@router.get(
    "/datasets/{dataset_id:int}/lineage",
    response_model=DatasetLineageNode,
    response_model_exclude_none=True,
)
def read_lineage(
    *,
    dataset_id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> DatasetLineageNode:
    """
    Walk this dataset's asserted upstreams, and their upstreams in turn.

    `derivations` gives one hop. This follows the chain, nesting each upstream
    under the dataset that names it. Only registered datasets have upstreams to
    nest; an external or described-only upstream is always a leaf.

    A dataset is expanded once per response. If the same one is reached again,
    by two paths or by a cycle, it appears as a stub marked `seen`. Branches cut
    short for other reasons are marked too: `restricted` where you may not read
    the upstream, `missing` where the derivation points at a dataset that has
    since been deleted.
    """
    return dataset_service.get_lineage(dataset_id, user=user)


@router.delete(
    "/datasets/{dataset_id:int}/derivations/{derivation_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_derivation(
    *,
    dataset_id: int,
    derivation_id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Retract an asserted upstream.
    """
    dataset_service.remove_derivation(
        dataset_id=dataset_id, derivation_id=derivation_id, user=user
    )


@router.post(
    "/datasets/{dataset_id:int}/distributions",
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
    "/datasets/{dataset_id:int}/distributions",
    response_model=list[DistributionRead],
    response_model_exclude_none=True,
)
def read_distributions(
    *,
    dataset_id: int,
    distribution_service: DistributionServiceDep,
    user: CurrentUserDep,
) -> list[DistributionRead]:
    """
    List all distributions for a dataset.
    """
    return [
        DistributionRead.model_validate(d)
        for d in distribution_service.get_for_dataset(dataset_id, user)
    ]


@router.patch(
    "/distributions/{distribution_id:int}",
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
    "/distributions/{distribution_id:int}",
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


@router.get(
    "/datasets/{dataset_id:int}/activity",
    response_model=ActivityRead,
)
def read_dataset_activity(
    *,
    dataset_id: int,
    dataset_service: DatasetServiceDep,
    user: CurrentUserDep,
) -> ActivityRead:
    """
    Retrieve the Activity that generated this dataset,
    including timestamps, parameters, and source version.
    Returns 404 if the dataset has no associated activity.
    """
    return ActivityRead.model_validate(dataset_service.get_activity(dataset_id, user))


@router.get(
    "/datasets/{dataset_id:int}/source",
    response_model=SourceRead,
)
def read_dataset_source(
    *,
    dataset_id: int,
    dataset_service: DatasetServiceDep,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> SourceRead:
    """
    Retrieve the Source (diagnostic system or code) that produced this dataset.
    Shortcut for dataset → activity → source. Returns 404 if the dataset has no activity.
    """
    activity = dataset_service.get_activity(dataset_id, user)
    return source_service.to_read_model(activity.source)
