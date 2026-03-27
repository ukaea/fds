from datetime import datetime

import pytest
from sqlmodel import Session, select

from app.models.dataset import Dataset
from app.models.file_access import CredentialRequest, S3Credentials
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.services.exceptions import ForbiddenError
from app.services.file_access_service import FileAccessService


@pytest.fixture
def access_service(session: Session):
    return FileAccessService(session=session)


def test_access_public_anonymous(access_service):
    """Public datasets should be accessible to anonymous users."""
    dataset = Dataset(
        name="pub", level=1, data_url="s3://pub", access_level=AccessLevel.PUBLIC
    )
    assert access_service._check_download_permission(ANONYMOUS_USER, dataset) is True


def test_access_public_authenticated(access_service):
    """Public datasets should be accessible to authenticated users."""
    user = AuthenticatedUser(id="u1", scopes=())
    dataset = Dataset(
        name="pub", level=1, data_url="s3://pub", access_level=AccessLevel.PUBLIC
    )
    assert access_service._check_download_permission(user, dataset) is True


def test_access_required_scope_allowed(access_service):
    """Dataset with required_scopes should be accessible to user having all listed scopes."""
    user = AuthenticatedUser(id="u1", scopes=("special:access",))
    dataset = Dataset(
        name="scoped",
        level=1,
        data_url="s3://scoped",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=["special:access"],
    )
    assert access_service._check_download_permission(user, dataset) is True


def test_access_required_scope_denied(access_service):
    """Dataset with required_scopes should be DENIED to user lacking any listed scope."""
    user = AuthenticatedUser(id="u1", scopes=("wrong:scope",))
    dataset = Dataset(
        name="scoped",
        level=1,
        data_url="s3://scoped",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=["special:access"],
    )
    assert access_service._check_download_permission(user, dataset) is False


def test_access_required_scope_overrides_fallback(
    access_service, mock_check_shot_operator
):
    """If required_scopes is set, fallback context check should NOT be called (Specific Overrides General)."""
    # User HAS shot operator (context), but LACKS required_scope.
    # Should FAIL.
    user = AuthenticatedUser(id="u1", scopes=("shot-operator:mast",))
    dataset = Dataset(
        name="override",
        level=1,
        data_url="s3://override",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=["special:top-secret"],
        device_name="mast",
    )

    allowed = access_service._check_download_permission(user, dataset)
    assert allowed is False
    # Ensure fallback was NOT called (optimization/strictness check)
    mock_check_shot_operator.assert_not_called()


def test_access_empty_required_scopes_auth_only_bypasses_fallback(
    access_service, mock_check_shot_operator
):
    """required_scopes=[] is an explicit auth-only gate and must bypass fallback."""
    user = AuthenticatedUser(id="u1", scopes=())
    dataset = Dataset(
        name="auth-only",
        level=1,
        data_url="s3://auth-only",
        access_level=AccessLevel.RESTRICTED,
        required_scopes=[],
        device_name="mast",
        shot_id="123",
    )

    assert access_service._check_download_permission(user, dataset) is True
    mock_check_shot_operator.assert_not_called()


def test_access_fallback_shot_context_allowed(access_service, mock_check_shot_operator):
    """If no required_scope, should fallback to Shot Context check."""
    user = AuthenticatedUser(id="u1", scopes=())
    dataset = Dataset(
        name="fallback",
        level=1,
        data_url="s3://fallback",
        access_level=AccessLevel.RESTRICTED,  # or Embargoed
        device_name="mast",
        shot_id="123",
    )
    # Mock fallback passing
    mock_check_shot_operator.return_value = None  # logic returns None on success

    assert access_service._check_download_permission(user, dataset) is True
    mock_check_shot_operator.assert_called_with(user, "mast")


def test_access_fallback_shot_context_denied(access_service, mock_check_shot_operator):
    """If no required_scope, should fallback to Shot Context check (failing)."""
    user = AuthenticatedUser(id="u1", scopes=())
    dataset = Dataset(
        name="fallback",
        level=1,
        data_url="s3://fallback",
        access_level=AccessLevel.RESTRICTED,
        device_name="mast",
        shot_id="123",
    )
    # Mock fallback failing
    mock_check_shot_operator.side_effect = ForbiddenError("Access denied")

    assert access_service._check_download_permission(user, dataset) is False


def test_fail_fast_malformed_url(access_service, mocker):
    """FileAccessService should propagate exceptions for malformed URLs (Fail Fast), not swallow them."""
    # Simulate urlparse raising ValueError (which happens for some bad IPv6 literals)
    # Verify we are mocking the usage in the service module
    mock_urlparse = mocker.patch("app.services.file_access_service.urlparse")
    mock_urlparse.side_effect = ValueError("Invalid URL")

    with pytest.raises(ValueError, match="Invalid URL"):
        access_service._group_urls_by_protocol(["http://bad-url"])


def test_polyglot_routing_s3(session, access_service, mock_s3_provider):
    user = AuthenticatedUser(id="user", scopes=())

    # 1. Setup DB with S3 dataset
    ds1 = Dataset(
        name="ds1", level=1, data_url="s3://bucket/ds1", access_level=AccessLevel.PUBLIC
    )
    session.add(ds1)
    session.commit()

    fake_cred = S3Credentials(
        access_key_id="k",
        secret_access_key="s",
        session_token="t",
        expiration=datetime.fromisoformat("2099-01-01T00:00:00+00:00"),
    )
    mock_s3_provider.generate_credentials.return_value = {"bucket": fake_cred}

    # 2. Call Service
    req = CredentialRequest(data_urls=["s3://bucket/ds1"])
    result = access_service.generate_session_credentials(user, req)

    # 3. Verify Routing
    mock_s3_provider.generate_credentials.assert_called_once()
    args = mock_s3_provider.generate_credentials.call_args
    assert "s3://bucket/ds1" in args[0][0]

    # Verify the URL is mapped to a credential in the manifest
    assert "s3://bucket/ds1" in result.resource_map


def test_empty_request_returns_empty(access_service, mock_s3_provider):
    user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    # Act
    result = access_service.generate_session_credentials(user, CredentialRequest())

    # Assert
    # Empty request should return empty manifest, not wildcard
    assert len(result.resource_map) == 0
    assert mock_s3_provider.generate_credentials.call_count == 0


def test_s3_provider_policy():
    pytest.importorskip("boto3")
    from app.core.storage.s3_provider import S3CredentialProvider

    provider = S3CredentialProvider()

    # Simple check
    pol = provider._construct_policy(["s3://b/k"])
    assert "arn:aws:s3:::b/k/*" in pol


def test_generate_session_credentials_integration(session, admin_user, mocker):
    """
    Integration test using in-memory DB to verify:
    1. Query filtering works (shot_id matching).
    2. Manifest generation works.
    """
    # 1. Setup Data
    # 1. Setup Data
    # Create Device first
    from app.models.device import Device

    device = Device(name="test-device", type="tokamak")
    session.add(device)
    session.commit()
    session.refresh(device)

    # Identify Shot ID
    shot_id = "12345"
    # Create Shot (AccessLevel.PUBLIC for simplicity)
    shot = Shot(id=shot_id, device_name=device.name, access_level=AccessLevel.PUBLIC)
    session.add(shot)
    session.commit()

    # Create 5 Datasets for this shot
    for i in range(5):
        ds = Dataset(
            name=f"signal_{i:02d}",
            level=1,
            shot_id=shot_id,
            device_name=device.name,
            data_url=f"s3://fds-data/shots/{shot_id}/signals/signal_{i:02d}",
            access_level=AccessLevel.PUBLIC,
            media_type="application/x-zarr",
        )
        session.add(ds)

    # Create 1 Dataset for a DIFFERENT shot (noise)
    other_shot_id = "999"
    other_shot = Shot(
        id=other_shot_id, device_name=device.name, access_level=AccessLevel.PUBLIC
    )
    session.add(other_shot)
    ds_noise = Dataset(
        name="noise",
        level=1,
        shot_id=other_shot_id,
        device_name=device.name,
        data_url="s3://fds-data/shots/999/noise",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(ds_noise)

    session.commit()

    # Verify data is in DB
    # Using Select instead of Query
    assert len(session.exec(select(Dataset)).all()) == 6

    # 2. Setup Service
    service = FileAccessService(session=session)
    request = CredentialRequest(shot_id=shot_id)

    # 3. Mock Provider to avoid calling AWS STS
    # We patch at the module level where FileAccessService imports it
    fake_cred = S3Credentials(
        access_key_id="fake",
        secret_access_key="fake",
        session_token="fake",
        expiration=datetime.fromisoformat("2099-01-01T00:00:00+00:00"),
    )
    mock_provider = mocker.MagicMock()
    mock_provider.generate_credentials.side_effect = lambda urls, name: {
        "fds-data": fake_cred
    }

    # Replace the provider interaction
    mocker.patch(
        "app.services.file_access_service.get_provider_for_protocol",
        return_value=mock_provider,
    )

    # 4. Execute
    manifest = service.generate_session_credentials(admin_user, request)

    # 5. Assertions
    # Should have found 5 datasets
    assert len(manifest.resource_map) == 5, (
        "Should return 5 datasets matching shot_id 12345"
    )

    # Should NOT include the noise dataset
    assert "s3://fds-data/shots/999/noise" not in manifest.resource_map

    # Check provider was called with correct URLs - we can use any call_args
    assert mock_provider.generate_credentials.call_count >= 1
