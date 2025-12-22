from fastapi import APIRouter, Depends, status

from app.api.deps import ShotServiceDep
from app.auth.security import get_current_user, AuthenticatedUser
from app.models.shot import (
    ShotCreate,
    ShotRead,
    ShotUpdate,
)

router = APIRouter()


@router.post(
    "/shots/",
    response_model=ShotRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_shot_global(
    *,
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ShotRead:
    """
    Create a new shot. Device name must be in the payload.
    """
    shot = shot_service.create(shot_in, user)
    return shot_service.to_read_model(shot)


@router.put(
    "/shots/{shot_id}",
    response_model=ShotRead,
    response_model_exclude_none=True,
)
def update_shot_global(
    *,
    shot_id: str,
    shot_in: ShotUpdate,
    shot_service: ShotServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ShotRead:
    """
    Update a shot globally.
    """
    db_obj = shot_service.get(shot_id)
    shot = shot_service.update(db_obj=db_obj, obj_in=shot_in, user=user)
    return shot_service.to_read_model(shot)


@router.post(
    "/devices/{device_name}/shots/",
    response_model=ShotRead,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
def create_shot_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ShotRead:
    """
    Create a new shot for a specific device. URL device name takes precedence.
    """
    shot = shot_service.create(shot_in, user, expected_device_name=device_name)
    return shot_service.to_read_model(shot)


@router.get(
    "/devices/{device_name}/shots/",
    response_model=list[ShotRead],
    response_model_exclude_none=True,
)
def read_shots_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    offset: int = 0,
    limit: int = 100,
    include_device: bool = False,
) -> list[ShotRead]:
    """
    Retrieve all shots for a specific device.
    """
    shots = shot_service.get_multi_by_device_name(
        device_name=device_name, offset=offset, limit=limit
    )

    return [shot_service.to_read_model(s, include_device=include_device) for s in shots]


@router.get(
    "/devices/{device_name}/shots/{shot_id}",
    response_model=ShotRead,
    response_model_exclude_none=True,
)
def read_shot_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_id: str,
) -> ShotRead:
    """
    Retrieve a shot specifically for a device context.
    """
    shot = shot_service.get_for_device(shot_id, device_name)
    return shot_service.to_read_model(shot)


@router.put(
    "/devices/{device_name}/shots/{shot_id}",
    response_model=ShotRead,
    response_model_exclude_none=True,
)
def update_shot_nested(
    *,
    device_name: str,
    shot_id: str,
    shot_in: ShotUpdate,
    shot_service: ShotServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> ShotRead:
    """
    Update a shot nested under a device.
    """
    db_obj = shot_service.get(shot_id)
    shot = shot_service.update(
        db_obj=db_obj, obj_in=shot_in, user=user, expected_device_name=device_name
    )
    return shot_service.to_read_model(shot)


@router.delete(
    "/devices/{device_name}/shots/{shot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shot_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """
    Delete a shot with authentication and optional context check.
    """
    shot_service.delete_with_auth(shot_id, user, expected_device_name=device_name)
    return None
