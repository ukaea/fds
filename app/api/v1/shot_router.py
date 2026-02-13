from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, DeviceServiceDep, ShotServiceDep
from app.models.shot import (
    ShotCreate,
    ShotRead,
    ShotUpdate,
)
from app.services.exceptions import DeviceNotFoundError, ResourceNotFoundError

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
    device_name: str,
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,
    shot_id: str,
    user: CurrentUserDep,
) -> ShotRead:
    """
    Retrieve a shot specifically for a device context.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise DeviceNotFoundError(f"Device '{device_name}' not found")

    shot = shot_service.get(shot_id, device.id)
    if not shot:
        raise ResourceNotFoundError(
            f"Shot '{shot_id}' not found for device '{device_name}'"
        )

    shot_service.check_read_access(shot, user)
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
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
) -> ShotRead:
    """
    Update a shot nested under a device.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise DeviceNotFoundError(f"Device '{device_name}' not found")

    db_obj = shot_service.get(shot_id, device.id)
    if not db_obj:
        raise ResourceNotFoundError(
            f"Shot '{shot_id}' not found for device '{device_name}'"
        )

    shot = shot_service.update(db_obj=db_obj, obj_in=shot_in, user=user)
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
    shot_service.delete_with_auth(shot_id, user, device_name=device_name)
    return None
