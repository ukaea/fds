from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserDep, DeviceServiceDep, SourceServiceDep
from app.models.device import DeviceCreate, DeviceRead, DeviceUpdate
from app.models.source import SourceCreate, SourceRead
from app.services.jsonld import map_device_to_dcat

router = APIRouter()


@router.post("/", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(
    *,
    device_service: DeviceServiceDep,
    device_in: DeviceCreate,
    user: CurrentUserDep,
) -> DeviceRead:
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
    user: CurrentUserDep,
) -> DeviceRead:
    """
    Update a device by name.
    """
    current_device = device_service.get_by_name(device_name)
    if not current_device:
        raise HTTPException(status_code=404, detail="Device not found")

    device = device_service.update(db_obj=current_device, obj_in=device_in, user=user)
    return device_service.to_read_model(device)


@router.delete("/{device_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    *,
    device_name: str,
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete a device by name.
    """
    deleted = device_service.delete(device_name, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    return None


@router.post(
    "/{device_name}/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_source_for_device(
    *,
    device_name: str,
    source_in: SourceCreate,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> SourceRead:
    """
    Create a new source linked to a specific device. Requires global admin.
    """
    # Force the device_name to match the path
    source_in.device_name = device_name
    source = source_service.create(source_in, user)
    return source_service.to_read_model(source)


@router.get(
    "/{device_name}/sources",
    response_model=list[SourceRead],
)
def read_sources_for_device(
    *,
    device_name: str,
    source_service: SourceServiceDep,
    offset: int = 0,
    limit: int = 100,
) -> list[SourceRead]:
    """
    Retrieve sources associated with a specific device.
    """
    sources = source_service.get_for_device(
        device_name=device_name, offset=offset, limit=limit
    )
    return source_service.to_read_models(sources)
