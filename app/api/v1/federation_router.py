from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DEFAULT_PAGE_SIZE, FederationServiceDep, Limit, Offset
from app.models.activity import ActivityType
from app.models.federation import DatasetQuery, FederatedSearch, MemberRead
from app.models.scope import CatalogueScope, DeviceScope
from app.services.jsonld import generate_context

router = APIRouter()


@router.get("/members", response_model=list[MemberRead])
def read_members(federation_service: FederationServiceDep) -> list[MemberRead]:
    """
    The other catalogues a search across catalogues asks, in the order their
    answers are reported.
    """
    return federation_service.list_members()


@router.get(
    "/datasets", response_model=FederatedSearch, response_model_exclude_none=True
)
def search_datasets(
    *,
    federation_service: FederationServiceDep,
    scope: CatalogueScope = CatalogueScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    shot_properties: Annotated[list[str] | None, Query(alias="shot_property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    shot_id_prefix: str | None = None,
    include_replaced: bool = False,
) -> FederatedSearch:
    """
    Ask every member catalogue for its datasets, as `GET /v1/datasets` lists
    this catalogue's.

    The filters and paging are those of `GET /v1/datasets`, and each member
    applies them to its own records: `offset` and `limit` page through each
    member's datasets separately. `activity_id` and the `include_*` options are
    not offered, since they refer to this catalogue's own records.

    The members are asked when the request arrives, anonymously, and nothing
    they return is kept. Each member's answer is reported on its own, in
    `answers`: its datasets as JSON-LD `dcat:Dataset` nodes written with the
    response's `@context`, or why it gave none. A dataset's `@id` is the
    member's own identifier for it.
    """
    query = DatasetQuery(
        scope=scope.value,
        name=name,
        properties=properties or [],
        shot_properties=shot_properties or [],
        activity_type=activity_type,
        source=source,
        shot_id_prefix=shot_id_prefix,
        include_replaced=include_replaced,
        offset=offset,
        limit=limit,
    )
    return FederatedSearch(
        context=generate_context(), answers=federation_service.search(query)
    )


@router.get(
    "/devices/{device_name}/datasets",
    response_model=FederatedSearch,
    response_model_exclude_none=True,
)
def search_device_datasets(
    *,
    federation_service: FederationServiceDep,
    device_name: str,
    scope: DeviceScope = DeviceScope.ALL,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    name: str | None = None,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    shot_properties: Annotated[list[str] | None, Query(alias="shot_property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    shot_id_prefix: str | None = None,
    include_replaced: bool = False,
) -> FederatedSearch:
    """
    Ask every member catalogue for its datasets on a device, as
    `GET /v1/devices/{device_name}/datasets` lists this catalogue's.

    The filters and paging are those of that listing, and each member applies
    them to its own records: `offset` and `limit` page through each member's
    datasets separately. A member that has no device of that name answers with
    no datasets. `activity_id` and the `include_*` options are not offered,
    since they refer to this catalogue's own records.

    The members are asked when the request arrives, anonymously, and nothing
    they return is kept. Each member's answer is reported on its own, in
    `answers`: its datasets as JSON-LD `dcat:Dataset` nodes written with the
    response's `@context`, or why it gave none. A dataset's `@id` is the
    member's own identifier for it.
    """
    query = DatasetQuery(
        device_name=device_name,
        scope=scope.value,
        name=name,
        properties=properties or [],
        shot_properties=shot_properties or [],
        activity_type=activity_type,
        source=source,
        shot_id_prefix=shot_id_prefix,
        include_replaced=include_replaced,
        offset=offset,
        limit=limit,
    )
    return FederatedSearch(
        context=generate_context(), answers=federation_service.search(query)
    )


@router.get(
    "/devices/{device_name}/shots/{shot_id}/datasets",
    response_model=FederatedSearch,
    response_model_exclude_none=True,
)
def search_shot_datasets(
    *,
    federation_service: FederationServiceDep,
    device_name: str,
    shot_id: str,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    include_replaced: bool = False,
) -> FederatedSearch:
    """
    Ask every member catalogue for its datasets on a shot, as
    `GET /v1/devices/{device_name}/shots/{shot_id}/datasets` lists this
    catalogue's.

    The filters and paging are those of that listing, and each member applies
    them to its own records: `offset` and `limit` page through each member's
    datasets separately. A member that has no such shot answers with no
    datasets. `activity_id` and the `include_*` options are not offered, since
    they refer to this catalogue's own records.

    The members are asked when the request arrives, anonymously, and nothing
    they return is kept. Each member's answer is reported on its own, in
    `answers`: its datasets as JSON-LD `dcat:Dataset` nodes written with the
    response's `@context`, or why it gave none. A dataset's `@id` is the
    member's own identifier for it.
    """
    query = DatasetQuery(
        device_name=device_name,
        shot_id=shot_id,
        properties=properties or [],
        activity_type=activity_type,
        source=source,
        include_replaced=include_replaced,
        offset=offset,
        limit=limit,
    )
    return FederatedSearch(
        context=generate_context(), answers=federation_service.search(query)
    )
