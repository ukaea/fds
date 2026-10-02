from fastapi import APIRouter

from app.api.deps import CurrentUserDep, FileAccessServiceDep
from app.models.file_access import CredentialManifest, CredentialRequest

router = APIRouter()


@router.post(
    "/credentials",
    response_model=CredentialManifest,
    response_model_exclude_none=True,
)
def get_data_access_credentials(
    access_service: FileAccessServiceDep,
    user: CurrentUserDep,
    request: CredentialRequest | None = None,
    include_storage_options: bool = False,
) -> CredentialManifest:
    """
    Vends temporary storage credentials for accessing datasets directly.

    Returns a manifest whose ``resource_map`` is keyed by dataset URL, each value
    holding the credential for that URL. Narrow what is vended for with
    ``device_name``, ``shot_id`` or ``data_urls``; a body naming none of them
    vends nothing, so that a stray empty request cannot ask for the whole
    catalogue.

    ``include_storage_options=true`` adds an opener-ready ``storage_options``
    rendering to each entry, the same shape the single-dataset endpoints return,
    alongside the raw credential.
    """
    if request is None:
        request = CredentialRequest()

    return access_service.generate_session_credentials(
        user=user,
        request=request,
        include_storage_options=include_storage_options,
    )
