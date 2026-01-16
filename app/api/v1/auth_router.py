from typing import Any

from fastapi import APIRouter

from app.api.deps import AccessServiceDep, CurrentUserDep

router = APIRouter()


@router.post("/credentials", response_model=dict[str, Any])
async def get_data_access_credentials(
    current_user: CurrentUserDep,
    access_service: AccessServiceDep,
) -> dict[str, Any]:
    """
    Vends temporary storage credentials for accessing datasets directly.
    Returns a dictionary keyed by provider (e.g. "s3", "azure").
    """
    credentials = access_service.generate_session_credentials(user=current_user)
    return credentials
