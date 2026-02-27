from datetime import datetime
from typing import Any

from pydantic import BaseModel


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
        from app.core.config import config

        opts = {
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
        from app.core.config import config

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


class CredentialRequest(BaseModel):
    """
    Filter for credential generation.
    """

    shot_id: str | None = None
    device_name: str | None = None
    data_urls: list[str] | None = None


class CredentialManifest(BaseModel):
    """
    Response model for multi-token vending.
    """

    tokens: list[dict[str, Any]]
    resource_map: dict[str, int]
