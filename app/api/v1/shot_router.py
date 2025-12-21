from typing import Union

from fastapi import APIRouter, Depends, status

from app.api.deps import DeviceServiceDep, ShotServiceDep
from app.api.permissions import require_device_admin
from app.auth.security import get_current_user, AuthenticatedUser
from app.models.mappers import ShotReadWithDevice
from app.models.shot import (
    Shot,
    ShotCreate,
    ShotRead,
    ShotUpdate,
)

router = APIRouter()


@router.post(
    "/shots/",
    response_model=ShotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shot_global(
    *,
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Shot:
    """
    Create a new shot. Device name must be in the payload.
    """
    return shot_service.create(shot_in, user)


@router.put(
    "/shots/{shot_id}",
    response_model=ShotRead,
)
def update_shot_global(
    *,
    shot_id: str,
    shot_in: ShotUpdate,
    shot_service: ShotServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Shot:
    """
    Update a shot globally.
    """
    db_obj = shot_service.get(shot_id)
    return shot_service.update(db_obj=db_obj, obj_in=shot_in, user=user)


@router.post(
    "/devices/{device_name}/shots/",
    response_model=ShotRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shot_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Shot:
    """
    Create a new shot for a specific device. URL device name takes precedence.
    """
    return shot_service.create(shot_in, user, expected_device_name=device_name)


@router.get("/devices/{device_name}/shots/", response_model=list[Union[ShotReadWithDevice, ShotRead]])
def read_shots_nested(
    *,
    device_name: str,
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,
    offset: int = 0,
    limit: int = 100,
    include_device: bool = False,
) -> list[ShotReadWithDevice | ShotRead]:
    """
    Retrieve all shots for a specific device.
    """
    # Context check via service
    device = device_service.get_by_name(device_name)
    shots = shot_service.get_multi_by_device(
        device_id=device.id, offset=offset, limit=limit
    )

    if include_device:
        return [ShotReadWithDevice.model_validate(s) for s in shots]
    return [ShotRead.model_validate(s) for s in shots]


@router.get("/devices/{device_name}/shots/{shot_id}", response_model=ShotRead)
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
    return ShotRead.model_validate(shot)


@router.put(
    "/devices/{device_name}/shots/{shot_id}",
    response_model=ShotRead,
)
def update_shot_nested(
    *,
    device_name: str,
    shot_id: str,
    shot_in: ShotUpdate,
    shot_service: ShotServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Shot:
    """
    Update a shot nested under a device.
    """
    db_obj = shot_service.get(shot_id)
    return shot_service.update(
        db_obj=db_obj, 
        obj_in=shot_in, 
        user=user, 
        expected_device_name=device_name
    )


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