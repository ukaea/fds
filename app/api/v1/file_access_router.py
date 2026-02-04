from fastapi import APIRouter

from app.api.deps import CurrentUserDep, FileAccessServiceDep
from app.models.file_access import CredentialManifest, CredentialRequest

router = APIRouter()


@router.post("/credentials", response_model=CredentialManifest)
def get_data_access_credentials(
    access_service: FileAccessServiceDep,
    user: CurrentUserDep,
    request: CredentialRequest | None = None,
) -> CredentialManifest:
    """
    Vends temporary storage credentials for accessing datasets directly.
    Returns a dictionary keyed by provider (e.g. "s3", "azure").
    """
    if request is None:
        request = CredentialRequest()

    manifest = access_service.generate_session_credentials(user=user, request=request)
    return manifest
