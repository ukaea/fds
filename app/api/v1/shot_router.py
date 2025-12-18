from typing import Union

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DeviceServiceDep, ShotServiceDep
from app.api.permissions import require_shot_admin
from app.models.mappers import ShotReadWithDevice
from app.models.shot import Shot, ShotCreate, ShotRead, ShotUpdate
from app.services.exceptions import DeviceNotFoundError

router = APIRouter()


@router.post(
    "/",
    response_model=ShotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_shot_admin)],
)
def create_shot(
    *,
    device_name: str,  # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,  # To resolve device_name to device_id
    shot_in: ShotCreate,
) -> Shot:
    """
    Create a new shot for a specific device.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Ensure the shot_in device_id matches the resolved device_id
    if shot_in.device_id != device.id:
        raise HTTPException(
            status_code=400,
            detail="The device_id in the request body must match the device specified in the path.",
        )

    try:
        shot = shot_service.create(shot_in)
        return shot
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/", response_model=list[Union[ShotReadWithDevice, ShotRead]])
def read_shots(
    *,
    device_name: str,  # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,  # To check if device exists
    offset: int = 0,
    limit: int = 100,
    include_device: bool = False,
) -> list[ShotReadWithDevice | ShotRead]:
    """
    Retrieve all shots for a specific device.
    Set `include_device=true` to include the associated device in the response.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shots = shot_service.get_multi_by_device(
        device_id=device.id, offset=offset, limit=limit
    )

    if include_device:
        return [ShotReadWithDevice.model_validate(s) for s in shots]
    return [ShotRead.model_validate(s) for s in shots]


@router.get("/{shot_id}", response_model=Union[ShotReadWithDevice, ShotRead])
def read_shot(
    *,
    device_name: str,  # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,  # To check if device exists
    shot_id: int,
    include_device: bool = False,
) -> ShotReadWithDevice | ShotRead:
    """
    Retrieve a single shot by ID for a specific device.
    Set `include_device=true` to include the associated device in the response.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shot = shot_service.get(shot_id)
    if not shot or shot.device_id != device.id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    if include_device:
        return ShotReadWithDevice.model_validate(shot)
    return ShotRead.model_validate(shot)


@router.put(
    "/{shot_id}",
    response_model=ShotRead,
    dependencies=[Depends(require_shot_admin)],
)
def update_shot(
    *,
    device_name: str,  # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,  # To check if device exists
    shot_id: int,
    shot_in: ShotUpdate,
) -> Shot:
    """
    Update a shot for a specific device.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    current_shot = shot_service.get(shot_id)
    if not current_shot or current_shot.device_id != device.id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    shot = shot_service.update(db_obj=current_shot, obj_in=shot_in)
    return shot


@router.delete(
    "/{shot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_shot_admin)],
)
def delete_shot(
    *,
    device_name: str,  # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep,  # To check if device exists
    shot_id: int,
) -> None:
    """
    Delete a shot for a specific device.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shot = shot_service.get(shot_id)
    if not shot or shot.device_id != device.id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    shot_service.delete(shot_id)
    return None
