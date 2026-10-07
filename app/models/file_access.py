from datetime import datetime

from pydantic import BaseModel

from .storage_options import (
    FsspecAzureStorageOptions,
    FsspecGCSStorageOptions,
    StorageOptions,
    StorageOptionsType,
    build_storage_options,
    parse_storage_url,
    storage_backend,
)


class S3Credentials(BaseModel):
    """
    Temporary S3/STS Access Credentials.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime
    endpoint_url: str | None = None
    region: str | None = None
    storage_options: StorageOptions | None = None
    """Opener-ready rendering of this credential.

    Populated only when the caller asks for it
    (``?include_storage_options=true``); ``None`` otherwise.
    """

    def to_storage_options(
        self,
        target_type: StorageOptionsType = StorageOptionsType.FSSPEC_S3,
        region: str | None = None,
    ) -> StorageOptions:
        """Render these credentials in the requested storage_options shape.

        ``region`` overrides the credential's stored region when set, allowing
        per-distribution region overrides to take effect at render time.
        """
        return build_storage_options(
            target_type,
            endpoint_url=self.endpoint_url,
            region=region or self.region,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            session_token=self.session_token,
        )


class AzureCredentials(BaseModel):
    """
    Temporary Azure SAS Token Credentials.
    """

    account_name: str
    sas_token: str
    storage_options: FsspecAzureStorageOptions | None = None
    """Opener-ready rendering of this credential, when the caller asks for it."""

    def to_storage_options(self) -> FsspecAzureStorageOptions:
        """Convert SAS token into FSSpec kwargs for adlfs."""
        return FsspecAzureStorageOptions(
            account_name=self.account_name, sas_token=self.sas_token
        )


class GCSCredentials(BaseModel):
    """
    Temporary GCS Downscoped Credentials.
    """

    token: str
    expiry: str | None = None
    storage_options: FsspecGCSStorageOptions | None = None
    """Opener-ready rendering of this credential, when the caller asks for it."""

    def to_storage_options(self) -> FsspecGCSStorageOptions:
        """Convert Downscoped token into FSSpec kwargs for gcsfs."""
        return FsspecGCSStorageOptions(token=self.token)


CredentialPayload = S3Credentials | AzureCredentials | GCSCredentials


class CredentialRequest(BaseModel):
    """
    Filter for credential generation.
    """

    shot_id: str | None = None
    device_name: str | None = None
    data_urls: list[str] | None = None


class CredentialManifest(BaseModel):
    """
    Maps each dataset URL to its temporary storage credential.

    Each value carries the raw credential fields. With
    ``include_storage_options=true`` it also carries ``storage_options``, the
    same opener-ready shape the single-dataset path returns.
    """

    resource_map: dict[str, CredentialPayload]


def anonymous_storage_options(
    data_url: str,
    target_type: StorageOptionsType | None,
    *,
    endpoint_url: str | None = None,
    region: str | None = None,
    account_name: str | None = None,
) -> StorageOptions | None:
    """Return storage options for anonymous access, by the URL's backend.

    S3 renders in ``target_type``'s shape, and a null ``target_type`` means the
    distribution opted out. Azure and GCS have one shape each and ignore it.
    ``account_name`` is used for an Azure URL that does not name its own.
    Returns ``None`` when there is nothing to render.
    """
    backend = storage_backend(data_url)
    if backend == "s3" and target_type is not None:
        return build_storage_options(
            target_type,
            endpoint_url=endpoint_url,
            region=region,
            anonymous=True,
        )
    if backend == "azure":
        # adlfs refuses an account_name that differs from the one in the URL.
        location = parse_storage_url(data_url)
        if location and location.account:
            account_name = location.account
        return FsspecAzureStorageOptions(account_name=account_name, anon=True)
    if backend == "gcs":
        return FsspecGCSStorageOptions(token="anon")
    return None
