from typing import Any, Protocol

from app.core.storage.gcs_provider import GCSCredentialProvider
from app.core.storage.s3_provider import S3CredentialProvider
from app.services.exceptions import ConfigurationError


class CredentialProvider(Protocol):
    """
    Protocol for vending temporary storage credentials.
    Abstractions allow supporting AWS, Azure, GCP, etc.
    """

    def generate_credentials(
        self, allowed_prefixes: list[str], session_name: str
    ) -> dict[str, Any]: ...


def get_provider_for_protocol(protocol: str) -> CredentialProvider:
    if protocol == "s3":
        return S3CredentialProvider()
    elif protocol in ("gs", "gcs"):
        return GCSCredentialProvider()

    raise ConfigurationError(f"No provider configured for protocol: {protocol}")
