from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserDep, ShotServiceDep
from app.models.shot import (
    ShotCreate,
    ShotRead,
    ShotUpdate,
)

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
    offset: int = 0,
    limit: int = 100,
    include_device: bool = False,
    include_annotations: bool = False,
    annotation: Annotated[list[str] | None, Query()] = None,
) -> list[ShotRead]:
    """
    Retrieve all shots for a specific device.

    `annotation` filters on the shot's `scientific_metadata`. Use `disruption` to
    match any shot that carries that annotation, or `confinement_mode:H-mode` to
    match a particular value. Repeat the parameter to require all of them.
    """
    shots = shot_service.get_multi_by_device_name(
        device_name=device_name,
        user=user,
        offset=offset,
        limit=limit,
        annotations=annotation,
    )

    return [
        shot_service.to_read_model(
            shot, include_device=include_device, include_annotations=include_annotations
        )
        for shot in shots
    ]


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
                str(request.base_url).rstrip("/"),
                include_annotations=include_annotations,
            ),
            media_type="application/ld+json",
        )
    return shot_service.to_read_model(
        shot, include_device=True, include_annotations=include_annotations
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
