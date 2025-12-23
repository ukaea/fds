from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth.security import get_current_user, AuthenticatedUser
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.api.deps import DeviceServiceDep
from app.services.jsonld import map_device_to_dcat

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
    return device_service.to_read_model(device)


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
    return [device_service.to_read_model(d) for d in devices]


@router.get("/{device_name}", response_model=DeviceRead)
def read_device(
    *,
    request: Request,
    device_service: DeviceServiceDep,
    device_name: str,
) -> DeviceRead | JSONResponse:
    """
    Retrieve a single device by name.
    Supports Content Negotiation:
    - Accept: application/ld+json -> Returns DCAT Metadata
    """
    device = device_service.get_by_name(device_name)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Content Negotiation
    if "application/ld+json" in request.headers.get("accept", ""):
        dcat_metadata = map_device_to_dcat(device, str(request.base_url).rstrip("/"))
        return JSONResponse(content=dcat_metadata, media_type="application/ld+json")

    return device_service.to_read_model(device)


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
    return device_service.to_read_model(device)


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
