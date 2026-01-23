from datetime import datetime

import pytest
from google.auth.exceptions import DefaultCredentialsError

from app.core.storage.gcs_provider import GCSCredentialProvider
from app.services.exceptions import ConfigurationError


@pytest.fixture
def mock_google_auth(mocker):
    mock_auth = mocker.patch("app.core.storage.gcs_provider.google.auth")
    mock_downscoped = mocker.patch(
        "app.core.storage.gcs_provider.google.auth.downscoped"
    )

    # Setup base credentials
    mock_creds = mocker.MagicMock()
    mock_auth.default.return_value = (mock_creds, "test-project")

    # Setup downscoped credentials
    mock_downscoped_creds = mocker.MagicMock()
    mock_downscoped_creds.token = "mock-downscoped-token"
    mock_downscoped_creds.expiry = datetime(2026, 1, 1, 12, 0, 0)
    mock_downscoped.Credentials.return_value = mock_downscoped_creds

    return mock_auth, mock_downscoped


def test_generate_credentials_success(mock_google_auth):
    """
    Test that generate_credentials correctly constructs the CAB rules
    and returns the expected map.
    """
    mock_auth, mock_downscoped = mock_google_auth

    provider = GCSCredentialProvider()
    prefixes = ["gs://my-bucket/data/file1", "gs://other-bucket/foo"]
    session_name = "test-session"

    result = provider.generate_credentials(prefixes, session_name)

    # Verify return structure
    assert "my-bucket" in result
    assert "other-bucket" in result
    assert result["my-bucket"]["token"] == "mock-downscoped-token"
    assert result["my-bucket"]["expiry"] == "2026-01-01T12:00:00"

    # Verify Logic
    # 1. Base credentials fetched
    mock_auth.default.assert_called_once()

    # 2. CAB Rules constructed correctly
    # Should be 2 rules, one for each bucket
    call_args = mock_downscoped.CredentialAccessBoundary.call_args
    assert call_args is not None
    rules = call_args.kwargs["rules"]
    assert len(rules) == 2

    resources = [r["availableResource"] for r in rules]
    assert "//storage.googleapis.com/projects/_/buckets/my-bucket" in resources
    assert "//storage.googleapis.com/projects/_/buckets/other-bucket" in resources

    # 3. Refresh called
    mock_downscoped.Credentials.return_value.refresh.assert_called_once()


def test_missing_credentials_configuration(mocker):
    """Test proper error when GOOGLE_APPLICATION_CREDENTIALS is missing."""
    mock_default = mocker.patch("app.core.storage.gcs_provider.google.auth.default")
    mock_default.side_effect = DefaultCredentialsError("Missing creds")

    provider = GCSCredentialProvider()

    with pytest.raises(ConfigurationError):
        provider.generate_credentials(["gs://bucket/key"], "session")


def test_requests_transport_used(mock_google_auth):
    """Verify that we initialize the credential with standard Requests transport."""
    _, mock_downscoped = mock_google_auth

    provider = GCSCredentialProvider()
    provider.generate_credentials(["gs://bucket"], "session")

    # Check that .refresh() was called with a google.auth.transport.requests.Request

    refresh_call = mock_downscoped.Credentials.return_value.refresh.call_args
    request_arg = refresh_call[0][0]

    assert request_arg.__class__.__name__ == "Request"
    assert request_arg.__module__ == "google.auth.transport.requests"
