from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from .storage_options import StorageOptions, StorageOptionsType, build_storage_options


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

    def to_storage_options(self) -> dict[str, Any]:
        """Convert SAS token into FSSpec kwargs for adlfs."""
        return {
            "account_name": self.account_name,
            "sas_token": self.sas_token,
        }


class GCSCredentials(BaseModel):
    """
    Temporary GCS Downscoped Credentials.
    """

    token: str
    expiry: str | None = None

    def to_storage_options(self) -> dict[str, Any]:
        """Convert Downscoped token into FSSpec kwargs for gcsfs."""
        return {
            "token": self.token,
        }


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
    """

    resource_map: dict[str, CredentialPayload]


def anonymous_storage_options(
    data_url: str,
    endpoint_url: str | None = None,
    region: str | None = None,
    target_type: StorageOptionsType = StorageOptionsType.FSSPEC_S3,
) -> StorageOptions | dict[str, Any] | None:
    """Return storage options for anonymous/public access based on URL scheme.

    For S3 URLs, returns a shape-specific :class:`StorageOptions` (``fsspec_s3``
    by default; pass ``target_type="icechunk_s3"`` for icechunk consumers).
    For Azure / GCS, returns the legacy plain-dict shape (Azure inherits public
    blob access from an empty dict; GCS uses the ``"anon"`` token convention).
    Returns ``None`` for unsupported schemes.
    """

    scheme = urlparse(data_url).scheme
    if scheme == "s3":
        return build_storage_options(
            target_type,
            endpoint_url=endpoint_url,
            region=region,
            anonymous=True,
        )
    if scheme in ("az", "abfs"):
        return {}
    if scheme == "gs":
        return {"token": "anon"}
    return None
