from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

from app.core.config import config
from app.models.file_access import AzureCredentials
from app.models.storage_options import parse_storage_url
from app.services.exceptions import ConfigurationError

DefaultAzureCredential: Any = None
BlobServiceClient: Any = None
ContainerSasPermissions: Any = None
generate_container_sas: Any = None

try:
    azure_identity = import_module("azure.identity")
    azure_blob = import_module("azure.storage.blob")

    DefaultAzureCredential = azure_identity.DefaultAzureCredential
    BlobServiceClient = azure_blob.BlobServiceClient
    ContainerSasPermissions = azure_blob.ContainerSasPermissions
    generate_container_sas = azure_blob.generate_container_sas
except ImportError:
    pass


class AzureCredentialProvider:
    """
    Vendor Azure User Delegation SAS tokens for containers.
    """

    def __init__(self, provider_config):
        self._provider_config = provider_config
        self._service_client = None

    def _require_azure_sdk(self) -> tuple[Any, Any, Any, Any]:
        if (
            DefaultAzureCredential is None
            or BlobServiceClient is None
            or ContainerSasPermissions is None
            or generate_container_sas is None
        ):
            raise ConfigurationError(
                "azure-storage-blob is not installed. "
                "Please install the 'azure' optional dependency: pip install 'fds[azure]'"
            )

        return (
            DefaultAzureCredential,
            BlobServiceClient,
            ContainerSasPermissions,
            generate_container_sas,
        )

    def generate_credentials(
        self, allowed_prefixes: list[str], _session_name: str
    ) -> dict[str, AzureCredentials]:
        """
        Generates a Map of Container -> SAS Token. URLs that are not Azure are skipped.
        """
        containers = {
            location.bucket
            for location in map(parse_storage_url, allowed_prefixes)
            if location and location.backend == "azure"
        }
        if not containers:
            return {}

        _, _, container_sas_permissions, gen_container_sas = self._require_azure_sdk()

        storage_account = self._provider_config.storage_account

        # 1. Get User Delegation Key
        # We need this to sign the SAS tokens on behalf of the AD identity (App Registration)
        service_client = self._get_service_client()

        now = datetime.now(UTC)
        # Key start time: safety buffer for clock skew
        key_start = now - timedelta(minutes=5)
        # Key expiry: Token duration + buffer
        key_expiry = now + timedelta(seconds=config.CREDENTIAL_TOKEN_DURATION + 300)

        try:
            ud_key = service_client.get_user_delegation_key(key_start, key_expiry)
        except Exception as e:  # noqa: BLE001 - SDK raises many types; all mean misconfiguration
            raise ConfigurationError(f"Failed to get Azure User Delegation Key: {e}")

        # 2. Generate SAS for each container
        result = {}
        sas_expiry = now + timedelta(seconds=config.CREDENTIAL_TOKEN_DURATION)
        permissions = container_sas_permissions(read=True, list=True)

        for container_name in containers:
            try:
                sas_token = gen_container_sas(
                    account_name=storage_account,
                    container_name=container_name,
                    user_delegation_key=ud_key,
                    permission=permissions,
                    expiry=sas_expiry,
                    start=key_start,
                )
                result[container_name] = AzureCredentials(
                    account_name=storage_account,
                    sas_token=sas_token,
                )
            except Exception as e:  # noqa: BLE001 - SDK raises many types; all mean misconfiguration
                # Log? Warning?
                # Failing one container shouldn't fail all?
                # For now, raise configuration error as it implies fundamental issue
                raise ConfigurationError(
                    f"Failed to generate SAS for {container_name}: {e}"
                )

        return result

    def _get_service_client(self):
        default_credential, blob_service_client, _, _ = self._require_azure_sdk()

        if not self._service_client:
            account_url = (
                f"https://{self._provider_config.storage_account}.blob.core.windows.net"
            )
            credential = default_credential()
            self._service_client = blob_service_client(
                account_url, credential=credential
            )
        return self._service_client
