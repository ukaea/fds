from collections.abc import Mapping
from typing import Protocol

from app.core.config import config
from app.models.file_access import CredentialPayload
from app.models.storage_options import StorageBackend


class CredentialProvider(Protocol):
    """
    Protocol for vending temporary storage credentials.
    Abstractions allow supporting AWS, Azure, GCP, etc.

    Returns a credential for each URL the provider can serve, keyed by that
    URL as given. A URL it cannot serve is left out.
    """

    def generate_credentials(
        self, urls: list[str], session_name: str, /
    ) -> Mapping[str, CredentialPayload]: ...


def get_provider_for_endpoint(
    backend: StorageBackend, endpoint_url: str | None
) -> CredentialProvider | None:
    """Return an initialised credential provider for a backend at an endpoint.

    Returns ``None`` when no provider is configured for the pair so callers can
    skip vending rather than raising.
    """
    provider_config = config.storage_provider(backend, endpoint_url)
    if provider_config is None:
        return None
    if provider_config.type == "s3":
        from app.core.storage.s3_provider import S3CredentialProvider

        return S3CredentialProvider(provider_config)
    if provider_config.type == "azure":
        from app.core.storage.azure_provider import AzureCredentialProvider

        return AzureCredentialProvider(provider_config)
    if provider_config.type == "gcs":
        from app.core.storage.gcs_provider import GCSCredentialProvider

        return GCSCredentialProvider(provider_config)
    return None
