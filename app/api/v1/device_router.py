from collections.abc import Sequence
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
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


@router.get("/", response_model=list[DeviceRead])
def read_devices(
    *,
    device_service: DeviceServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[Device]:
    """
    Retrieve all devices.
    """
    devices = device_service.get_multi(offset=offset, limit=limit)
    return devices


@router.get("/{device_id}", response_model=DeviceRead)
def read_device(*, device_service: DeviceServiceDep, device_id: int) -> Device:
    """
    Retrieve a single device by ID.
    """
    device = device_service.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


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
