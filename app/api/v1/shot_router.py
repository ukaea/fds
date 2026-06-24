from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserDep, ShotServiceDep
from app.models.shot import (
    ShotCreate,
    ShotRead,
    ShotUpdate,
)
from app.services.jsonld import map_shot_to_dcat

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
) -> list[ShotRead]:
    """
    Retrieve all shots for a specific device.
    """
    shots = shot_service.get_multi_by_device_name(
        device_name=device_name, user=user, offset=offset, limit=limit
    )

    return [shot_service.to_read_model(s, include_device=include_device) for s in shots]


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
) -> ShotRead | JSONResponse:
    """
    Retrieve a shot specifically for a device context.
    Supports content negotiation: Accept: application/ld+json returns DCAT JSON-LD.
    """
    shot = shot_service.get_by_device_name(shot_id, device_name, user)
    if "application/ld+json" in request.headers.get("accept", ""):
        return JSONResponse(
            content=map_shot_to_dcat(shot, str(request.base_url).rstrip("/")),
            media_type="application/ld+json",
        )
    return shot_service.to_read_model(shot, include_device=True)


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
    return None
