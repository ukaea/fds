from typing import Any

from fastapi import APIRouter

from app.api.deps import BaseURLDep, CurrentUserDep, DeviceServiceDep
from app.api.negotiation import JSONLDResponse
from app.services.jsonld import map_catalog_to_dcat

router = APIRouter()


@router.get("/catalog", response_model=dict[str, Any], response_class=JSONLDResponse)
def get_catalog(
    device_service: DeviceServiceDep,
    user: CurrentUserDep,
    base: BaseURLDep,
) -> dict[str, Any]:
    """
    Returns the root Data Catalog (DCAT) for the Fusion Data Service.
    This catalog aggregates all Devices (as sub-catalogs). Its `@id` is the
    catalogue's identifier, `/catalog`, which carries no API version.
    """
    return map_catalog_to_dcat(device_service.get_multi(user=user), base)
