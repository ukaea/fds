from typing import Any, Dict

from fastapi import APIRouter, Request, Depends
from sqlmodel import Session, select

from app.core.db import get_session
from app.models.device import Device
from app.services.jsonld import generate_context, map_device_to_dcat

router = APIRouter()


@router.get("/catalog", response_model=Dict[str, Any])
def get_catalog(
    request: Request,
    session: Session = Depends(get_session),
) -> Dict[str, Any]:
    """
    Returns the root Data Catalog (DCAT) for the Fusion Data Service.
    This catalog aggregates all Devices (as sub-catalogs).
    """
    base_url = str(request.base_url).rstrip("/")

    # Root Catalog Metadata
    catalog = {
        "@context": generate_context(),
        "@type": "dcat:Catalog",
        "@id": f"{base_url}/api/v1/catalog",
        "title": "Fusion Data Service Catalog",
        "description": "A centralized catalog for fusion energy data.",
        "publisher": "Fusion Data Service",
    }

    # List all devices as sub-catalogs
    devices = session.exec(select(Device)).all()
    sub_catalogs = []

    for device in devices:
        dcat_device = map_device_to_dcat(device, base_url)
        sub_catalogs.append(dcat_device)

    catalog["dcat:catalog"] = sub_catalogs

    return catalog
