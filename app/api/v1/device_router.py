from fastapi import APIRouter, Depends, HTTPException

from app.auth.security import get_current_user, AuthenticatedUser
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.api.deps import DeviceServiceDep

router = APIRouter()


@router.post("/", response_model=DeviceRead)
def create_device(
    *,
    device_service: DeviceServiceDep,
    device_in: DeviceCreate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Device:
    """
    Create a new device.
    """
    device = device_service.create(device_in, user)
    return device


@router.get("/", response_model=list[DeviceRead])
def read_devices(
    *,
    device_service: DeviceServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> list[DeviceRead]:
    """
    Retrieve all devices.
    """
    devices = device_service.get_multi(offset=offset, limit=limit)
    return [DeviceRead.model_validate(d) for d in devices]


@router.get("/{device_name}", response_model=DeviceRead)
def read_device(
    *,
    device_service: DeviceServiceDep,
    device_name: str,
) -> DeviceRead:
    """
    Retrieve a single device by name.
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return DeviceRead.model_validate(device)


@router.put("/{device_name}", response_model=DeviceRead)
def update_device(
    *,
    device_service: DeviceServiceDep,
    device_name: str,
    device_in: DeviceUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Device:
    """
    Update a device by name.
    """
    current_device = device_service.get_by_name(device_name)
    if not current_device:
        raise HTTPException(status_code=404, detail="Device not found")

    device = device_service.update(db_obj=current_device, obj_in=device_in, user=user)
    return device


@router.delete("/{device_name}")
def delete_device(
    *,
    device_service: DeviceServiceDep,
    device_name: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """
    Delete a device by name.
    """
    current_device = device_service.get_by_name(device_name)
    if not current_device:
        raise HTTPException(status_code=404, detail="Device not found")

    device_service.delete(current_device.id, user)
    return {"ok": True}
