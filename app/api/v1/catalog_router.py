from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import CurrentUserDep, DeviceServiceDep
from app.services.jsonld import generate_context, map_device_to_dcat

router = APIRouter()


@router.get("/catalog", response_model=dict[str, Any])
def get_catalog(
    request: Request,
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    """
    Returns the root Data Catalog (DCAT) for the Fusion Data Service.
    This catalog aggregates all Devices (as sub-catalogs).
    """
    base_url = str(request.base_url).rstrip("/")

    # Root Catalog Metadata
    catalog: dict[str, Any] = {
        "@context": generate_context(),
        "@type": "dcat:Catalog",
        "@id": f"{base_url}/v1/catalog",
        "title": "Fusion Data Service Catalog",
        "description": "A centralized catalog for fusion energy data.",
        "publisher": "Fusion Data Service",
    }

    # List all devices as sub-catalogs
    devices = device_service.get_multi(user=user)
    sub_catalogs: list[dict[str, Any]] = []

    for device in devices:
        dcat_device = map_device_to_dcat(device, base_url)
        sub_catalogs.append(dcat_device)

    catalog["dcat:catalog"] = sub_catalogs

    return catalog
