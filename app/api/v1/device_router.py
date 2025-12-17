from typing import Union

from fastapi import APIRouter, Depends, HTTPException

from app.api.permissions import require_admin
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.models.mappers import DeviceReadWithShots
from app.api.deps import DeviceServiceDep

router = APIRouter()


@router.post("/", response_model=DeviceRead, dependencies=[Depends(require_admin)])
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


@router.get("/{device_name}", response_model=Union[DeviceReadWithShots, DeviceRead])
def read_device(
    *,
    device_service: DeviceServiceDep,
    device_name: str,
    include_shots: bool = False,
) -> DeviceReadWithShots | DeviceRead:
    """
    Retrieve a single device by name.
    Set `include_shots=true` to include the device's shots in the response.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if include_shots:
        return DeviceReadWithShots.model_validate(device)
    return DeviceRead.model_validate(device)


@router.put("/{device_name}", response_model=DeviceRead, dependencies=[Depends(require_admin)])
def update_device(
    *,
    device_service: DeviceServiceDep,
    device_name: str,
    device_in: DeviceUpdate,
) -> Device:
    """
    Update a device by name.
    """
    current_device = device_service.get_by_name(device_name)
    if not current_device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device = device_service.update(current_device.id, device_in)
    return device


@router.delete("/{device_name}", dependencies=[Depends(require_admin)])
def delete_device(*, device_service: DeviceServiceDep, device_name: str) -> dict:
    """
    Delete a device by name.
    """
    current_device = device_service.get_by_name(device_name)
    if not current_device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    device_service.delete(current_device.id)
    return {"ok": True}
