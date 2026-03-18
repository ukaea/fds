from collections.abc import Mapping
from typing import Protocol

from app.models.file_access import CredentialPayload
from app.services.exceptions import ConfigurationError


class CredentialProvider(Protocol):
    """
    Protocol for vending temporary storage credentials.
    Abstractions allow supporting AWS, Azure, GCP, etc.
    """

    def generate_credentials(
        self, allowed_prefixes: list[str], session_name: str
    ) -> Mapping[str, CredentialPayload]: ...


def get_provider_for_protocol(protocol: str) -> CredentialProvider:
    if protocol == "s3":
        from app.core.storage.s3_provider import S3CredentialProvider

        return S3CredentialProvider()
    elif protocol in ("gs", "gcs"):
        from app.core.storage.gcs_provider import GCSCredentialProvider

        return GCSCredentialProvider()
    elif protocol in ("az", "abfs"):
        from app.core.storage.azure_provider import AzureCredentialProvider

        return AzureCredentialProvider()

    raise ConfigurationError(f"No provider configured for protocol: {protocol}")
