from typing import Annotated, Union
from fastapi import APIRouter, Depends, HTTPException, status

from app.models.shot import Shot, ShotCreate, ShotRead, ShotUpdate
from app.models.mappers import ShotReadWithDevice
from app.services.exceptions import DeviceNotFoundError
from app.services.shot_service import ShotService
from app.services.device_service import DeviceService # Needed to check if device exists
from app.core.db import SessionDep

router = APIRouter()


def get_shot_service(session: SessionDep) -> ShotService:
    return ShotService(session)


ShotServiceDep = Annotated[ShotService, Depends(get_shot_service)]


def get_device_service(session: SessionDep) -> DeviceService:
    return DeviceService(session)

DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]


@router.post("/", response_model=ShotRead, status_code=status.HTTP_201_CREATED)
def create_shot(
    *,
    device_id: int, # Path parameter from the parent router
    shot_service: ShotServiceDep,
    shot_in: ShotCreate,
) -> Shot:
    """
    Create a new shot for a specific device.
    """
    # Ensure the shot_in device_id matches the path device_id
    if shot_in.device_id != device_id:
        raise HTTPException(
            status_code=400,
            detail="The device_id in the request body must match the device_id in the path.",
        )

    try:
        shot = shot_service.create(shot_in)
        return shot
    except DeviceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/", response_model=list[Union[ShotReadWithDevice, ShotRead]])
def read_shots(
    *,
    device_id: int, # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep, # To check if device exists
    offset: int = 0,
    limit: int = 100,
    include_device: bool = False,
) -> list[ShotReadWithDevice | ShotRead]:
    """
    Retrieve all shots for a specific device.
    Set `include_device=true` to include the associated device in the response.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shots = shot_service.get_multi_by_device(device_id=device_id, offset=offset, limit=limit)

    if include_device:
        return [ShotReadWithDevice.model_validate(s) for s in shots]
    return [ShotRead.model_validate(s) for s in shots]


@router.get("/{shot_id}", response_model=Union[ShotReadWithDevice, ShotRead])
def read_shot(
    *,
    device_id: int, # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep, # To check if device exists
    shot_id: int,
    include_device: bool = False,
) -> ShotReadWithDevice | ShotRead:
    """
    Retrieve a single shot by ID for a specific device.
    Set `include_device=true` to include the associated device in the response.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shot = shot_service.get(shot_id)
    if not shot or shot.device_id != device_id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    if include_device:
        return ShotReadWithDevice.model_validate(shot)
    return ShotRead.model_validate(shot)


@router.put("/{shot_id}", response_model=ShotRead)
def update_shot(
    *,
    device_id: int, # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep, # To check if device exists
    shot_id: int,
    shot_in: ShotUpdate,
) -> Shot:
    """
    Update a shot for a specific device.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    current_shot = shot_service.get(shot_id)
    if not current_shot or current_shot.device_id != device_id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    shot = shot_service.update(shot_id, shot_in)
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot


@router.delete("/{shot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shot(
    *,
    device_id: int, # Path parameter from the parent router
    shot_service: ShotServiceDep,
    device_service: DeviceServiceDep, # To check if device exists
    shot_id: int,
) -> None:
    """
    Delete a shot for a specific device.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shot = shot_service.get(shot_id)
    if not shot or shot.device_id != device_id:
        raise HTTPException(status_code=404, detail="Shot not found for this device")

    shot_service.delete(shot_id)
    return None
