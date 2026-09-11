from collections.abc import Mapping
from typing import Protocol

from app.core.config import config
from app.models.file_access import CredentialPayload


class CredentialProvider(Protocol):
    """
    Protocol for vending temporary storage credentials.
    Abstractions allow supporting AWS, Azure, GCP, etc.
    """

    def generate_credentials(
        self, allowed_prefixes: list[str], session_name: str, /
    ) -> Mapping[str, CredentialPayload]: ...


def get_provider_for_endpoint(endpoint_url: str | None) -> CredentialProvider | None:
    """Return an initialised credential provider for the given storage endpoint URL.

    Searches ``config.STORAGE_PROVIDERS`` for a matching entry keyed by
    ``endpoint_url``.  Returns ``None`` when no provider is configured for that
    endpoint so callers can skip vending rather than raising.
    """
    for provider_config in config.STORAGE_PROVIDERS:
        if provider_config.endpoint_url != endpoint_url:
            continue
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
