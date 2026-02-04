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
