import pytest

from app.core.storage.azure_provider import AzureCredentialProvider
from app.services.exceptions import ConfigurationError


@pytest.fixture
def mock_azure_blobs(mocker):
    # Mock Config
    mocker.patch(
        "app.core.storage.azure_provider.config.AZURE_STORAGE_ACCOUNT", "testaccount"
    )
    mocker.patch(
        "app.core.storage.azure_provider.config.CREDENTIAL_TOKEN_DURATION", 3600
    )

    # Mock Azure SDK modules
    mocker.patch("app.core.storage.azure_provider.DefaultAzureCredential")
    mock_service_client = mocker.patch(
        "app.core.storage.azure_provider.BlobServiceClient"
    )
    mock_gen_sas = mocker.patch(
        "app.core.storage.azure_provider.generate_container_sas"
    )

    # Setup Service Client mock
    mock_client_instance = mocker.MagicMock()
    mock_service_client.return_value = mock_client_instance

    # Setup User Delegation Key
    mock_key = mocker.MagicMock()
    mock_client_instance.get_user_delegation_key.return_value = mock_key

    # Setup SAS Generation
    mock_gen_sas.return_value = "sp=r&st=2026..."

    return {"client": mock_client_instance, "gen_sas": mock_gen_sas, "key": mock_key}


def test_generate_credentials_success(mock_azure_blobs):
    """
    Test that generate_credentials gets a delegation key and mints SAS tokens per container.
    """
    provider = AzureCredentialProvider()
    prefixes = ["az://container1/path", "abfs://container2/data"]

    result = provider.generate_credentials(prefixes, "session")

    # Verify results
    assert "container1" in result
    assert "container2" in result
    assert result["container1"].sas_token == "sp=r&st=2026..."

    # Verify Logic
    mocks = mock_azure_blobs

    # 1. User Delegation Key requested
    mocks["client"].get_user_delegation_key.assert_called_once()

    # 2. SAS generated for each container
    assert mocks["gen_sas"].call_count == 2

    # Check arguments for one of the calls
    call_args_list = mocks["gen_sas"].call_args_list
    containers_called = [c.kwargs["container_name"] for c in call_args_list]
    assert "container1" in containers_called
    assert "container2" in containers_called

    # Check Account Name
    assert call_args_list[0].kwargs["account_name"] == "testaccount"

    # Check User Delegation Key passed
    assert call_args_list[0].kwargs["user_delegation_key"] == mocks["key"]


def test_missing_storage_account(mocker):
    """Test error when AZURE_STORAGE_ACCOUNT is not set."""
    mocker.patch("app.core.storage.azure_provider.config.AZURE_STORAGE_ACCOUNT", None)
    # Be sure to mock DefaultAzureCredential so we don't hit import error check first if running without deps
    mocker.patch("app.core.storage.azure_provider.DefaultAzureCredential")

    provider = AzureCredentialProvider()
    with pytest.raises(ConfigurationError, match="AZURE_STORAGE_ACCOUNT"):
        provider.generate_credentials(["az://c/p"], "s")


def test_sas_generation_error(mock_azure_blobs, mocker):
    """Test error handling during SAS generation."""
    mocks = mock_azure_blobs
    # Make generation fail
    mocks["gen_sas"].side_effect = Exception("SAS Failure")

    provider = AzureCredentialProvider()
    with pytest.raises(ConfigurationError, match="Failed to generate SAS"):
        provider.generate_credentials(["az://c/p"], "s")
