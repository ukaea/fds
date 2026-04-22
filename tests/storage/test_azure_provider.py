import pytest

from app.core.config import AzureStorageProvider
from app.core.storage.azure_provider import AzureCredentialProvider
from app.services.exceptions import ConfigurationError

PROVIDER_CONFIG = AzureStorageProvider(storage_account="testaccount")


@pytest.fixture
def mock_azure_blobs(mocker):
    mocker.patch(
        "app.core.storage.azure_provider.config.CREDENTIAL_TOKEN_DURATION", 3600
    )

    mocker.patch("app.core.storage.azure_provider.DefaultAzureCredential")
    mock_service_client = mocker.patch(
        "app.core.storage.azure_provider.BlobServiceClient"
    )
    mock_gen_sas = mocker.patch(
        "app.core.storage.azure_provider.generate_container_sas"
    )

    mock_client_instance = mocker.MagicMock()
    mock_service_client.return_value = mock_client_instance

    mock_key = mocker.MagicMock()
    mock_client_instance.get_user_delegation_key.return_value = mock_key

    mock_gen_sas.return_value = "sp=r&st=2026..."

    return {"client": mock_client_instance, "gen_sas": mock_gen_sas, "key": mock_key}


def test_generate_credentials_success(mock_azure_blobs):
    """
    Test that generate_credentials gets a delegation key and mints SAS tokens per container.
    """
    provider = AzureCredentialProvider(PROVIDER_CONFIG)
    prefixes = ["az://container1/path", "abfs://container2/data"]

    result = provider.generate_credentials(prefixes, "session")

    assert "container1" in result
    assert "container2" in result
    assert result["container1"].sas_token == "sp=r&st=2026..."

    mocks = mock_azure_blobs
    mocks["client"].get_user_delegation_key.assert_called_once()
    assert mocks["gen_sas"].call_count == 2

    call_args_list = mocks["gen_sas"].call_args_list
    containers_called = [c.kwargs["container_name"] for c in call_args_list]
    assert "container1" in containers_called
    assert "container2" in containers_called
    assert call_args_list[0].kwargs["account_name"] == "testaccount"
    assert call_args_list[0].kwargs["user_delegation_key"] == mocks["key"]


def test_sas_generation_error(mock_azure_blobs):
    """Test error handling during SAS generation."""
    mocks = mock_azure_blobs
    mocks["gen_sas"].side_effect = Exception("SAS Failure")

    provider = AzureCredentialProvider(PROVIDER_CONFIG)
    with pytest.raises(ConfigurationError, match="Failed to generate SAS"):
        provider.generate_credentials(["az://c/p"], "s")
