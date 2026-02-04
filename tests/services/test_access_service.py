import pytest
from sqlmodel import Session

from app.models.dataset import Dataset
from app.models.identity import AuthenticatedUser

# Guard S3 imports - boto3 optional
from app.models.policy import AccessLevel
from app.services.file_access_service import FileAccessService


# --- Test Service Logic (Polyglot) ---
@pytest.fixture
def mock_s3_provider(mocker):
    # Mock the get_provider_for_protocol to return a mock S3 provider
    mock_prov = mocker.Mock()
    # When initialized, S3CredentialProvider will be used, but we want to intercept the factory
    mocker.patch(
        "app.services.file_access_service.get_provider_for_protocol",
        return_value=mock_prov,
    )
    return mock_prov


@pytest.fixture
def access_service(session: Session, mock_s3_provider):
    return FileAccessService(session=session)


def test_polyglot_routing_s3(session, access_service, mock_s3_provider):
    user = AuthenticatedUser(id="user", scopes=[])

    # 1. Setup DB with S3 dataset
    ds1 = Dataset(
        name="ds1", level=1, data_url="s3://bucket/ds1", access_level=AccessLevel.PUBLIC
    )
    session.add(ds1)
    session.commit()

    # 2. Call Service
    from app.models.file_access import CredentialRequest

    # Must specify explicit request now (no implicit "select all")
    req = CredentialRequest(data_urls=["s3://bucket/ds1"])
    result = access_service.generate_session_credentials(user, req)

    # 3. Verify Routing
    # Should have called get_provider_for_protocol("s3") -> mock_s3_provider
    # Then mock_s3_provider.generate_credentials(...)
    mock_s3_provider.generate_credentials.assert_called_once()

    # Verify allowed_urls passed to provider
    args = mock_s3_provider.generate_credentials.call_args
    assert "s3://bucket/ds1" in args[0][0]

    # Verify Result Structure
    # result is CredentialManifest. tokens is list[dict].
    # Check if we have a token for s3
    s3_tokens = [t for t in result.tokens if t["provider"] == "s3"]
    assert len(s3_tokens) > 0
    # Check that the token credentials match the mock return
    assert (
        s3_tokens[0]["credentials"]
        == mock_s3_provider.generate_credentials.return_value
    )


def test_empty_request_returns_empty(access_service, mock_s3_provider):
    user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    # Act
    from app.models.file_access import CredentialRequest

    result = access_service.generate_session_credentials(user, CredentialRequest())

    # Assert
    # Empty request should return empty manifest, not wildcard
    assert len(result.tokens) == 0
    assert len(result.resource_map) == 0
    assert mock_s3_provider.generate_credentials.call_count == 0


# --- Test Provider Logic ---


def test_s3_provider_policy():
    pytest.importorskip("boto3")
    from app.core.storage.s3_provider import S3CredentialProvider

    provider = S3CredentialProvider()

    # Simple check
    pol = provider._construct_policy(["s3://b/k"])
    assert "arn:aws:s3:::b/k/*" in pol
