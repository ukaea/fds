from typing import Annotated, Union
from fastapi import APIRouter, Depends, HTTPException

from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.models.mappers import DeviceReadWithShots
from app.services.device_service import DeviceService
from app.core.db import SessionDep

router = APIRouter()


def get_device_service(session: SessionDep) -> DeviceService:
    return DeviceService(session)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]


@router.post("/", response_model=DeviceRead)
def create_device(
    *,
    device_service: DeviceServiceDep,
    device_in: DeviceCreate,
) -> Device:
    """
    Create a new device.
    """
    device = device_service.create(device_in)
    return device


@router.get("/", response_model=list[Union[DeviceReadWithShots, DeviceRead]])
def read_devices(
    *,
    device_service: DeviceServiceDep,
    offset: int = 0,
    limit: int = 100,
    include_shots: bool = False,
) -> list[DeviceReadWithShots | DeviceRead]:
    """
    Retrieve all devices.
    Set `include_shots=true` to include the device's shots in the response.
    """
    devices = device_service.get_multi(offset=offset, limit=limit)
    if include_shots:
        return [DeviceReadWithShots.model_validate(d) for d in devices]
    return [DeviceRead.model_validate(d) for d in devices]


@router.get("/{device_id}", response_model=Union[DeviceReadWithShots, DeviceRead])
def read_device(
    *,
    device_service: DeviceServiceDep,
    device_id: int,
    include_shots: bool = False,
) -> DeviceReadWithShots | DeviceRead:
    """
    Retrieve a single device by ID.
    Set `include_shots=true` to include the device's shots in the response.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if include_shots:
        return DeviceReadWithShots.model_validate(device)
    return DeviceRead.model_validate(device)


@router.put("/{device_id}", response_model=DeviceRead)
def update_device(
    *,
    device_service: DeviceServiceDep,
    device_id: int,
    device_in: DeviceUpdate,
) -> Device:
    """
    Update a device.
    """
    device = device_service.update(device_id, device_in)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.delete("/{device_id}")
def delete_device(*, device_service: DeviceServiceDep, device_id: int) -> dict:
    """
    Delete a device.
    """
    device = device_service.delete(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True}
