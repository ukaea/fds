from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    DEFAULT_PAGE_SIZE,
    BaseURLDep,
    CurrentUserDep,
    Limit,
    Offset,
    ShotServiceDep,
)
from app.models.available_properties import AvailableProperties, PropertyValues
from app.models.shot import (
    ShotCreate,
    ShotRead,
    ShotUpdate,
)
from app.services.available_properties import DEFAULT_MAX_VALUES

router = APIRouter()


@router.post(
    "/devices/{device_name}/shots",
    response_model=ShotRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_shot(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
    user: CurrentUserDep,
) -> ShotRead:
    """
    Create a new shot for a specific device. URL device name takes precedence.
    """
    shot = shot_service.create(shot_in, user, expected_device_name=device_name)
    return shot_service.to_read_model(shot)


@router.get(
    "/devices/{device_name}/shots",
    response_model=list[ShotRead],
    response_model_exclude_none=True,
)
def read_shots(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    include_device: bool = False,
    include_annotations: bool = False,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    property_min: Annotated[list[str] | None, Query()] = None,
    property_max: Annotated[list[str] | None, Query()] = None,
    id_prefix: str | None = None,
) -> list[ShotRead]:
    """
    Retrieve all shots for a specific device.

    `property` filters on the shot's `scientific_metadata`. Use `disruption`
    to match any shot carrying that name, or `confinement_mode:H-mode` to match
    a value. Repeat the parameter to give more than one: two values of the same
    property match a shot with either, while values of different properties must
    all match.

    `property_min` and `property_max` bound a numeric value, as
    `plasma_current_max:700000`. Values that are not numbers are skipped rather
    than matched.

    `id_prefix` keeps the shots whose ID starts with it, so `304` finds
    30400 to 30499.
    """
    shots = shot_service.get_multi_by_device_name(
        device_name=device_name,
        user=user,
        offset=offset,
        limit=limit,
        properties=properties,
        minimums=property_min,
        maximums=property_max,
        id_prefix=id_prefix,
    )

    return [
        shot_service.to_read_model(
            shot,
            include_device=include_device,
            include_annotations=include_annotations,
            user=user,
        )
        for shot in shots
    ]


# Declared before /shots/{shot_id}: the paths have the same shape, so the other
# order would bind shot_id to the literal "annotations". Reserving a segment this
# way is what /datasets/id/{id} already does ahead of /datasets/{name}.
@router.get(
    "/devices/{device_name}/shots/properties",
    response_model=AvailableProperties,
    response_model_exclude_none=True,
)
def read_shot_properties(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
    properties: Annotated[list[str] | None, Query(alias="property")] = None,
    property_min: Annotated[list[str] | None, Query()] = None,
    property_max: Annotated[list[str] | None, Query()] = None,
    max_values: int = DEFAULT_MAX_VALUES,
    id_prefix: str | None = None,
) -> AvailableProperties:
    """
    The properties this device's shots carry, for building a filter.

    One entry per property name, with how many shots carry it, how many
    distinct values it has, and the values themselves when there are at most
    `max_values` of them. A missing `values` alongside a large `distinct` marks
    a measurement or free text: filter on the name's presence, not on a value.

    `property` takes the same forms as the listing and narrows the scope, so
    `total` is the number of matching shots. So does `id_prefix`.
    """
    return shot_service.available_properties(
        device_name=device_name,
        user=user,
        properties=properties,
        minimums=property_min,
        maximums=property_max,
        max_values=max_values,
        id_prefix=id_prefix,
    )


# Declared before /shots/{shot_id} for the same reason as the properties route: one
# path segment after /shots/, so the other order binds shot_id to "properties".
@router.get(
    "/devices/{device_name}/shots/properties/{name}/values",
    response_model=PropertyValues,
    response_model_exclude_none=True,
)
def read_shot_property_values(
    *,
    device_name: str,
    name: str,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
    q: str | None = None,
    limit: int = 50,
) -> PropertyValues:
    """
    The values one scientific-metadata name takes, with a count per value.

    For a vocabulary too large for the properties listing to enumerate. `q` matches
    values containing it, case-insensitively, and the most common come first.
    """
    return shot_service.property_values(
        device_name=device_name,
        name=name,
        user=user,
        query=q,
        limit=limit,
    )


@router.get(
    "/devices/{device_name}/shots/{shot_id}",
    response_model=ShotRead,
    response_model_exclude_none=True,
)
def read_shot(
    *,
    request: Request,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_id: str,
    user: CurrentUserDep,
    include_annotations: bool = False,
    base: BaseURLDep,
) -> ShotRead | JSONResponse:
    """
    Retrieve a shot specifically for a device context.
    Supports content negotiation: Accept: application/ld+json returns DCAT JSON-LD.
    """
    shot = shot_service.get_by_device_name(shot_id, device_name, user)
    if "application/ld+json" in request.headers.get("accept", ""):
        return JSONResponse(
            content=shot_service.to_dcat(
                shot,
                base,
                include_annotations=include_annotations,
                user=user,
            ),
            media_type="application/ld+json",
        )
    return shot_service.to_read_model(
        shot, include_device=True, include_annotations=include_annotations, user=user
    )


@router.put(
    "/devices/{device_name}/shots/{shot_id}",
    response_model=ShotRead,
    response_model_exclude_none=True,
)
def update_shot(
    *,
    device_name: str,
    shot_id: str,
    shot_in: ShotUpdate,
    shot_service: ShotServiceDep,
    user: CurrentUserDep,
) -> ShotRead:
    """
    Update a shot nested under a device.
    """
    shot = shot_service.update(
        shot_id=shot_id, device_name=device_name, obj_in=shot_in, user=user
    )
    return shot_service.to_read_model(shot)


@router.delete(
    "/devices/{device_name}/shots/{shot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shot(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_id: str,
    user: CurrentUserDep,
) -> None:
    """
    Delete a shot with authentication and optional context check.
    """
    shot_service.delete(shot_id, user, device_name=device_name)
