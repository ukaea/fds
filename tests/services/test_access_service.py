import pytest
from sqlmodel import Session

# Guard S3 imports - boto3 optional
from app.models.common import AccessLevel
from app.models.dataset import Dataset
from app.models.user import AuthenticatedUser
from app.services.access_service import AccessService


# --- Test Service Logic (Polyglot) ---
@pytest.fixture
def mock_s3_provider(mocker):
    # Mock the get_provider_for_protocol to return a mock S3 provider
    mock_prov = mocker.Mock()
    # When initialized, S3CredentialProvider will be used, but we want to intercept the factory
    mocker.patch(
        "app.services.access_service.get_provider_for_protocol", return_value=mock_prov
    )
    return mock_prov


@pytest.fixture
def access_service(session: Session, mock_s3_provider):
    return AccessService(session=session)


def test_polyglot_routing_s3(session, access_service, mock_s3_provider):
    user = AuthenticatedUser(id="user", scopes=[])

    # 1. Setup DB with S3 dataset
    ds1 = Dataset(
        name="ds1", level=1, data_url="s3://bucket/ds1", access_level=AccessLevel.PUBLIC
    )
    session.add(ds1)
    session.commit()

    # 2. Call Service
    result = access_service.generate_session_credentials(user)

    # 3. Verify Routing
    # Should have called get_provider_for_protocol("s3") -> mock_s3_provider
    # Then mock_s3_provider.generate_credentials(...)
    mock_s3_provider.generate_credentials.assert_called_once()

    # Verify allowed_urls passed to provider
    args = mock_s3_provider.generate_credentials.call_args
    assert "s3://bucket/ds1" in args[0][0]

    # Verify Result Structure
    assert "s3" in result
    assert result["s3"] == mock_s3_provider.generate_credentials.return_value


def test_admin_wildcard(access_service, mock_s3_provider):
    user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    # Act
    access_service.generate_session_credentials(user)

    # Assert
    # AccessService iterates over SUPPORTED_PROTOCOLS used in the implementation
    # Currently ["s3", "gs"]

    # The mock is returned for ALL calls to get_provider_for_protocol
    # So we expect it to be called once for "s3" and once for "gs" (if gs is in supported lists)
    assert mock_s3_provider.generate_credentials.call_count >= 1

    # Check that at least one call passed ["*"]
    calls = mock_s3_provider.generate_credentials.call_args_list
    # Each call is (args, kwargs). args[0] is the list of urls.

    found_wildcard = False
    for call in calls:
        if call[0][0] == ["*"]:
            found_wildcard = True

    assert found_wildcard, "Provider should have been called with ['*']"


# --- Test Provider Logic ---


def test_s3_provider_policy():
    pytest.importorskip("boto3")
    from app.core.storage.s3_provider import S3CredentialProvider

    provider = S3CredentialProvider()

    # Simple check
    pol = provider._construct_policy(["s3://b/k"])
    assert "arn:aws:s3:::b/k/*" in pol
