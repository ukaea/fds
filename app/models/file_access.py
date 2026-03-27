from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from app.core.config import config


class S3Credentials(BaseModel):
    """
    Temporary S3/STS Access Credentials.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    def to_storage_options(self) -> dict[str, Any]:
        """Convert STS token attributes into FSSpec kwargs seamlessly."""
        opts: dict[str, Any] = {
            "key": self.access_key_id,
            "secret": self.secret_access_key,
            "token": self.session_token,
            "client_kwargs": {},
        }
        if config.STS_ENDPOINT_URL:
            opts["client_kwargs"]["endpoint_url"] = config.STS_ENDPOINT_URL
        return opts


class AzureCredentials(BaseModel):
    """
    Temporary Azure SAS Token Credentials.
    """

    sas_token: str

    def to_storage_options(self) -> dict[str, Any]:
        """Convert SAS token into FSSpec kwargs for adlfs."""
        return {
            "account_name": config.AZURE_STORAGE_ACCOUNT,
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


def anonymous_storage_options(data_url: str) -> dict[str, Any] | None:
    """
    Return FSSpec storage options for anonymous/public access based on URL scheme.
    Returns None for unsupported schemes.

    Note: Azure public blobs are accessible without credentials when no SAS token
    is provided; adlfs infers anonymous access from the empty options dict.
    """
    scheme = urlparse(data_url).scheme
    if scheme == "s3":
        opts: dict[str, Any] = {"anon": True}
        if config.STS_ENDPOINT_URL:
            opts["client_kwargs"] = {"endpoint_url": config.STS_ENDPOINT_URL}
        return opts
    if scheme in ("az", "abfs"):
        return {}
    if scheme == "gs":
        return {"token": "anon"}
    return None
