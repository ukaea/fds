from datetime import datetime

import pytest
from sqlmodel import Session, select

from app.core.config import AzureStorageProvider, S3StorageProvider
from app.core.storage.azure_provider import AzureCredentialProvider
from app.core.storage.s3_provider import S3CredentialProvider
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.distribution import Distribution
from app.models.file_access import AzureCredentials, CredentialRequest, S3Credentials
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.models.storage_options import (
    FsspecS3StorageOptions,
    IcechunkS3StorageOptions,
    StorageLocation,
    StorageOptionsType,
)
from app.services.exceptions import ForbiddenError
from app.services.file_access_service import FileAccessService, ResolvedDistribution


@pytest.fixture
def access_service(session: Session):
    return FileAccessService(session=session)


def test_access_public_anonymous(access_service):
    """Public datasets should be accessible to anonymous users."""
    dataset = Dataset(name="pub", level=1, access_level=AccessLevel.PUBLIC)
    assert access_service._check_download_permission(ANONYMOUS_USER, dataset) is True


def test_access_public_authenticated(access_service):
    """Public datasets should be accessible to authenticated users."""
    user = AuthenticatedUser(id="u1", scopes=())
    dataset = Dataset(name="pub", level=1, access_level=AccessLevel.PUBLIC)
    assert access_service._check_download_permission(user, dataset) is True


def test_access_required_scope_allowed(access_service):
    """Dataset with required_scopes should be accessible to user having all listed scopes."""
    user = AuthenticatedUser(id="u1", scopes=("special:access",))
    dataset = Dataset(
        name="scoped",
        level=1,
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
        access_level=AccessLevel.RESTRICTED,
        device_name="mast",
        shot_id="123",
    )
    # Mock fallback failing
    mock_check_shot_operator.side_effect = ForbiddenError("Access denied")

    assert access_service._check_download_permission(user, dataset) is False


def test_fail_fast_malformed_url(access_service):
    """FileAccessService should propagate exceptions for malformed URLs (Fail Fast), not swallow them."""
    with pytest.raises(ValueError, match="Invalid IPv6 URL"):
        access_service._group_by_endpoint(
            [ResolvedDistribution("s3://[bad/key", None, None, None)]
        )


def test_polyglot_routing_s3(session, access_service, mock_credential_provider):
    user = AuthenticatedUser(id="user", scopes=())

    # 1. Setup DB with S3 dataset
    ds1 = Dataset(name="ds1", level=1, access_level=AccessLevel.PUBLIC)
    session.add(ds1)
    session.flush()
    assert ds1.id is not None
    session.add(
        Distribution(
            dataset_id=ds1.id, url="s3://bucket/ds1", default_distribution=True
        )
    )
    session.commit()

    fake_cred = S3Credentials(
        access_key_id="k",
        secret_access_key="s",
        session_token="t",
        expiration=datetime.fromisoformat("2099-01-01T00:00:00+00:00"),
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/ds1": fake_cred
    }

    # 2. Call Service
    req = CredentialRequest(data_urls=["s3://bucket/ds1"])
    result = access_service.generate_session_credentials(user, req)

    # 3. Verify Routing
    mock_credential_provider.generate_credentials.assert_called_once()
    args = mock_credential_provider.generate_credentials.call_args
    assert "s3://bucket/ds1" in args[0][0]

    # Verify the URL is mapped to a credential in the manifest
    assert "s3://bucket/ds1" in result.resource_map


def test_providers_sharing_an_endpoint_each_get_their_own_urls(
    session, access_service, mocker
):
    """AWS S3 and Azure both leave ``endpoint_url`` unset, so the URL's scheme
    has to pick between them, whichever is listed first."""
    mocker.patch(
        "app.core.storage.providers.config.STORAGE_PROVIDERS",
        [
            S3StorageProvider(endpoint_url=None, region="r", sts_role_arn="arn:test"),
            AzureStorageProvider(storage_account="acct"),
        ],
    )

    def vend(credential):
        def generate(_provider, urls, _session_name):
            return dict.fromkeys(urls, credential)

        return generate

    mocker.patch.object(
        S3CredentialProvider, "generate_credentials", vend(_fake_s3_credentials())
    )
    mocker.patch.object(
        AzureCredentialProvider,
        "generate_credentials",
        vend(AzureCredentials(account_name="acct", sas_token="sas")),
    )
    _public_dataset_with_distribution(session, url="s3://bucket/a")
    _public_dataset_with_distribution(session, url="az://container/b")

    manifest = access_service.generate_session_credentials(
        AuthenticatedUser(id="user", scopes=()),
        CredentialRequest(data_urls=["s3://bucket/a", "az://container/b"]),
    )

    assert isinstance(manifest.resource_map["s3://bucket/a"], S3Credentials)
    assert isinstance(manifest.resource_map["az://container/b"], AzureCredentials)


def test_empty_request_returns_empty(access_service, mock_credential_provider):
    user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    # Act
    result = access_service.generate_session_credentials(user, CredentialRequest())

    # Assert
    # Empty request should return empty manifest, not wildcard
    assert len(result.resource_map) == 0
    assert mock_credential_provider.generate_credentials.call_count == 0


def test_s3_provider_policy():
    """Single-object URLs must grant both the exact-object ARN (for NetCDF /
    blob GetObject) and the prefix ARN with ``/*`` (for Zarr / IceChunk store
    contents). See ``S3CredentialProvider._to_arns``.
    """
    pytest.importorskip("boto3")
    provider = S3CredentialProvider(
        S3StorageProvider(
            endpoint_url=None, region="us-east-1", sts_role_arn="arn:test"
        )
    )

    pol = provider._construct_policy([StorageLocation("s3", "b", "k")])
    assert "arn:aws:s3:::b/k" in pol
    assert "arn:aws:s3:::b/k/*" in pol


def test_s3_provider_policy_wildcard_url():
    """URLs already ending in ``*`` are preserved as-is — no double-suffix."""
    pytest.importorskip("boto3")
    provider = S3CredentialProvider(
        S3StorageProvider(
            endpoint_url=None, region="us-east-1", sts_role_arn="arn:test"
        )
    )

    pol = provider._construct_policy([StorageLocation("s3", "b", "prefix/*")])
    assert "arn:aws:s3:::b/prefix/*" in pol
    assert "arn:aws:s3:::b/prefix/*/*" not in pol


def test_generate_session_credentials_integration(session, admin_user, mocker):
    """
    Integration test using in-memory DB to verify:
    1. Query filtering works (shot_id matching).
    2. Manifest generation works.
    """
    # 1. Setup Data
    # 1. Setup Data
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
            access_level=AccessLevel.PUBLIC,
        )
        session.add(ds)
        session.flush()
        assert ds.id is not None
        session.add(
            Distribution(
                dataset_id=ds.id,
                url=f"s3://fds-data/shots/{shot_id}/signals/signal_{i:02d}",
                media_type="application/x-zarr",
                default_distribution=True,
            )
        )

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
        access_level=AccessLevel.PUBLIC,
    )
    session.add(ds_noise)
    session.flush()
    assert ds_noise.id is not None
    session.add(
        Distribution(
            dataset_id=ds_noise.id,
            url="s3://fds-data/shots/999/noise",
            default_distribution=True,
        )
    )

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
    mock_provider.generate_credentials.side_effect = lambda urls, name: dict.fromkeys(
        urls, fake_cred
    )

    # Replace the provider interaction
    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
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


# --- storage_options parity with the single-dataset path ---------------------


def _public_dataset_with_distribution(session, **distribution_kwargs) -> None:
    """Register one public dataset whose distribution carries the given fields."""
    ds = Dataset(
        name=distribution_kwargs["url"].rsplit("/", 1)[-1],
        level=1,
        access_level=AccessLevel.PUBLIC,
    )
    session.add(ds)
    session.flush()
    assert ds.id is not None
    session.add(
        Distribution(dataset_id=ds.id, default_distribution=True, **distribution_kwargs)
    )
    session.commit()


def _fake_s3_credentials(endpoint_url: str | None = None, region: str | None = None):
    return S3Credentials(
        access_key_id="k",
        secret_access_key="s",
        session_token="t",
        expiration=datetime.fromisoformat("2099-01-01T00:00:00+00:00"),
        endpoint_url=endpoint_url,
        region=region,
    )


def test_storage_options_absent_unless_asked(
    session, access_service, mock_credential_provider
):
    """The default response is unchanged: the raw credential and nothing more."""
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/plain",
        storage_options_type=StorageOptionsType.FSSPEC_S3,
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/plain": _fake_s3_credentials()
    }

    manifest = access_service.generate_session_credentials(
        user, CredentialRequest(data_urls=["s3://bucket/plain"])
    )

    assert manifest.resource_map["s3://bucket/plain"].storage_options is None


def test_storage_options_fsspec_shape(
    session, access_service, mock_credential_provider
):
    """An fsspec distribution renders s3fs kwargs, splat-ready for xarray."""
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/zarr",
        endpoint_url="https://s3.example.org",
        storage_options_type=StorageOptionsType.FSSPEC_S3,
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/zarr": _fake_s3_credentials(endpoint_url="https://s3.example.org")
    }

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(data_urls=["s3://bucket/zarr"]),
        include_storage_options=True,
    )

    entry = manifest.resource_map["s3://bucket/zarr"]
    assert entry.storage_options is not None
    dumped = entry.storage_options.model_dump(exclude_none=True)
    assert dumped == {
        "key": "k",
        "secret": "s",
        "token": "t",
        "client_kwargs": {"endpoint_url": "https://s3.example.org"},
    }
    # The raw credential is still there for callers that want it.
    assert entry.access_key_id == "k"


def test_storage_options_icechunk_fills_endpoint_defaults(
    session, access_service, mock_credential_provider
):
    """A non-AWS plain-http endpoint gets force_path_style and allow_http.

    These are properties of the endpoint rather than of the credential, so a
    hand-written mapping misses them; omitting force_path_style against an
    S3-compatible store gives a connection that resolves but finds no bucket.
    """
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/store",
        endpoint_url="http://s3.echo.example.ac.uk",
        media_type="application/vnd.icechunk+zarr",
        storage_options_type=StorageOptionsType.ICECHUNK_S3,
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/store": _fake_s3_credentials(
            endpoint_url="http://s3.echo.example.ac.uk"
        )
    }

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(data_urls=["s3://bucket/store"]),
        include_storage_options=True,
    )

    options = manifest.resource_map["s3://bucket/store"].storage_options
    assert options is not None
    dumped = options.model_dump(exclude_none=True)
    assert dumped["allow_http"] is True
    assert dumped["force_path_style"] is True
    assert dumped["access_key_id"] == "k"
    # bucket/prefix stay the caller's choice.
    assert "bucket" not in dumped


def test_storage_options_are_per_url_not_shared(
    session, access_service, mock_credential_provider
):
    """Two URLs on one credential render their own shapes.

    The S3 provider returns a single credential object for every URL, so
    rendering has to copy rather than mutate.
    """
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/as-fsspec",
        endpoint_url="https://s3.example.org",
        storage_options_type=StorageOptionsType.FSSPEC_S3,
    )
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/as-icechunk",
        endpoint_url="https://s3.example.org",
        storage_options_type=StorageOptionsType.ICECHUNK_S3,
    )
    shared = _fake_s3_credentials(endpoint_url="https://s3.example.org")
    mock_credential_provider.generate_credentials.return_value = dict.fromkeys(
        ["s3://bucket/as-fsspec", "s3://bucket/as-icechunk"], shared
    )

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(
            data_urls=["s3://bucket/as-fsspec", "s3://bucket/as-icechunk"]
        ),
        include_storage_options=True,
    )

    fsspec = manifest.resource_map["s3://bucket/as-fsspec"].storage_options
    icechunk = manifest.resource_map["s3://bucket/as-icechunk"].storage_options
    assert fsspec is not None and icechunk is not None
    assert isinstance(fsspec, FsspecS3StorageOptions)
    assert isinstance(icechunk, IcechunkS3StorageOptions)
    # The provider's own object is untouched.
    assert shared.storage_options is None


def test_storage_options_region_override_from_distribution(
    session, access_service, mock_credential_provider
):
    """A Distribution region overrides the provider's, as on the dataset path."""
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session,
        url="s3://bucket/regional",
        endpoint_url="https://s3.example.org",
        region="eu-west-2",
        storage_options_type=StorageOptionsType.FSSPEC_S3,
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/regional": _fake_s3_credentials(
            endpoint_url="https://s3.example.org", region="us-east-1"
        )
    }

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(data_urls=["s3://bucket/regional"]),
        include_storage_options=True,
    )

    options = manifest.resource_map["s3://bucket/regional"].storage_options
    assert options is not None
    assert options.model_dump()["client_kwargs"]["region_name"] == "eu-west-2"


def test_storage_options_skipped_when_distribution_opts_out(
    session, access_service, mock_credential_provider
):
    """A null storage_options_type is an opt-out, same as on the dataset path."""
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session, url="s3://bucket/opted-out", storage_options_type=None
    )
    mock_credential_provider.generate_credentials.return_value = {
        "s3://bucket/opted-out": _fake_s3_credentials()
    }

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(data_urls=["s3://bucket/opted-out"]),
        include_storage_options=True,
    )

    entry = manifest.resource_map["s3://bucket/opted-out"]
    assert entry.storage_options is None
    assert entry.access_key_id == "k"


def test_storage_options_azure_entry(session, access_service, mock_credential_provider):
    """Azure has one shape and no target type, so it renders regardless."""
    user = AuthenticatedUser(id="user", scopes=())
    _public_dataset_with_distribution(
        session, url="az://container/blob", storage_options_type=None
    )
    mock_credential_provider.generate_credentials.return_value = {
        "az://container/blob": AzureCredentials(account_name="acct", sas_token="sas")
    }

    manifest = access_service.generate_session_credentials(
        user,
        CredentialRequest(data_urls=["az://container/blob"]),
        include_storage_options=True,
    )

    entry = manifest.resource_map["az://container/blob"]
    assert entry.storage_options is not None
    assert entry.storage_options.model_dump(exclude_none=True) == {
        "account_name": "acct",
        "sas_token": "sas",
    }
