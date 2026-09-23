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

    Returns a manifest whose ``resource_map`` is keyed by dataset URL, each value
    holding the credential for that URL. Narrow what is vended for with
    ``device_name``, ``shot_id`` or ``data_urls``; an omitted body vends for every
    dataset the caller is allowed to read.
    """
    if request is None:
        request = CredentialRequest()

    manifest = access_service.generate_session_credentials(user=user, request=request)
    return manifest
