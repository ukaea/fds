from datetime import datetime

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate, DatasetScope, DatasetUpdate
from app.models.device import DeviceCreate
from app.models.file_access import CredentialManifest, S3Credentials
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.models.storage_options import (
    FsspecS3StorageOptions,
    IcechunkS3StorageOptions,
    StorageOptionsType,
)
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import ForbiddenError, ResourceNotFoundError
from app.services.shot_service import ShotService


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="dataset_service")
def dataset_service_fixture(session: Session) -> DatasetService:
    return DatasetService(session)


def test_create_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    shot = shot_service.create(
        ShotCreate(id="shot-101", device_name="Test Device"), user=admin_user
    )
    assert shot.id == "shot-101"

    dataset_create = DatasetCreate(
        name="core_profiles",
        level=2,
        url="s3://test-bucket/shot-101/core_profiles.zarr",
        quality_flag="good",
        shot_id=shot.id,
        device_name="Test Device",
    )
    dataset = dataset_service.create(dataset_create, user=admin_user)

    assert dataset.id is not None
    assert dataset.name == "core_profiles"
    assert dataset.level == 2
    assert (
        dataset.distributions[0].url == "s3://test-bucket/shot-101/core_profiles.zarr"
    )
    assert dataset.quality_flag == "good"
    assert dataset.shot_id == shot.id


def test_create_dataset_for_nonexistent_shot(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    device_service = DeviceService(dataset_service.session)
    device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )

    dataset_create = DatasetCreate(
        name="nonexistent_data",
        level=1,
        url="s3://nonexistent",
        shot_id="nonexistent-shot",
        device_name="Test Device",
    )
    with pytest.raises(ResourceNotFoundError):
        dataset_service.create(dataset_create, user=admin_user)


def test_get_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    shot = shot_service.create(
        ShotCreate(id="shot-101", device_name="Test Device"), user=admin_user
    )
    assert shot.id == "shot-101"

    created_dataset = dataset_service.create(
        DatasetCreate(
            name="mag_diag",
            level=1,
            url="s3://url",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )

    retrieved_dataset = dataset_service.get(created_dataset.id)
    assert retrieved_dataset is not None
    assert retrieved_dataset.id == created_dataset.id
    assert retrieved_dataset.name == "mag_diag"


def test_get_dataset_not_found(dataset_service: DatasetService):
    retrieved_dataset = dataset_service.get(999)
    assert retrieved_dataset is None


def test_get_dataset_by_name_in_context(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(
        DeviceCreate(name="Device Resolve", type="Test"), user=admin_user
    )
    shot_service.create(
        ShotCreate(id="shot-resolve", device_name="Device Resolve"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="resolved_dataset",
            level=1,
            url="s3://resolved",
            shot_id="shot-resolve",
            device_name="Device Resolve",
        ),
        user=admin_user,
    )

    results = dataset_service.get_by_name_in_context(
        name="resolved_dataset",
        user=admin_user,
        device_name="Device Resolve",
        shot_id="shot-resolve",
    )

    assert len(results) == 1
    assert results[0].name == "resolved_dataset"


def test_get_dataset_by_name_in_context_returns_empty_when_missing(
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    results = dataset_service.get_by_name_in_context(
        name="missing",
        user=admin_user,
    )
    assert results == []


def test_get_datasets(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    shot = shot_service.create(
        ShotCreate(id="shot-101", device_name="Test Device"), user=admin_user
    )
    assert shot.id == "shot-101"

    dataset_service.create(
        DatasetCreate(
            name="data1",
            level=1,
            url="url1",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(
            name="data2",
            level=2,
            url="url2",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )

    datasets = dataset_service.get_multi(user=admin_user)
    assert len(datasets) == 2


def test_get_datasets_for_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device1 = device_service.create(
        DeviceCreate(name="Device 1", type="Type A"), user=admin_user
    )
    assert device1.id is not None
    shot1 = shot_service.create(
        ShotCreate(id="shot-1", device_name="Device 1"), user=admin_user
    )
    assert shot1.id == "shot-1"

    device2 = device_service.create(
        DeviceCreate(name="Device 2", type="Type B"), user=admin_user
    )
    assert device2.id is not None
    shot2 = shot_service.create(
        ShotCreate(id="shot-2", device_name="Device 2"), user=admin_user
    )
    assert shot2.id == "shot-2"

    dataset_service.create(
        DatasetCreate(
            name="shot1_data1",
            level=1,
            url="url_s1_d1",
            shot_id=shot1.id,
            device_name="Device 1",
        ),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(
            name="shot1_data2",
            level=2,
            url="url_s1_d2",
            shot_id=shot1.id,
            device_name="Device 1",
        ),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(
            name="shot2_data1",
            level=1,
            url="url_s2_d1",
            shot_id=shot2.id,
            device_name="Device 2",
        ),
        user=admin_user,
    )

    datasets_shot1 = dataset_service.get_datasets_for_shot(
        shot1.id, "Device 1", user=admin_user
    )
    assert len(datasets_shot1) == 2
    assert all(ds.shot_id == shot1.id for ds in datasets_shot1)

    datasets_shot2 = dataset_service.get_datasets_for_shot(
        shot2.id, "Device 2", user=admin_user
    )
    assert len(datasets_shot2) == 1
    assert all(ds.shot_id == shot2.id for ds in datasets_shot2)


def test_get_datasets_for_device_scopes(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="Device X", type="Type X"), user=admin_user)
    device_service.create(DeviceCreate(name="Device Y", type="Type Y"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="shot-1", device_name="Device X"), user=admin_user
    )
    shot_service.create(
        ShotCreate(id="shot-2", device_name="Device Y"), user=admin_user
    )

    device_ds = dataset_service.create(
        DatasetCreate(
            name="device_data",
            level=1,
            url="url_device",
            device_name="Device X",
        ),
        user=admin_user,
    )
    shot_ds = dataset_service.create(
        DatasetCreate(
            name="shot_data",
            level=1,
            url="url_shot",
            device_name="Device X",
            shot_id=shot.id,
        ),
        user=admin_user,
    )
    # Another device's shot dataset must not leak into Device X's listing.
    dataset_service.create(
        DatasetCreate(
            name="other_device_data",
            level=1,
            url="url_other",
            device_name="Device Y",
            shot_id="shot-2",
        ),
        user=admin_user,
    )

    all_datasets = dataset_service.get_datasets_for_device("Device X", user=admin_user)
    assert {ds.id for ds in all_datasets} == {device_ds.id, shot_ds.id}

    device_only = dataset_service.get_datasets_for_device(
        "Device X", user=admin_user, scope=DatasetScope.DEVICE
    )
    assert [ds.id for ds in device_only] == [device_ds.id]
    assert device_only[0].shot_id is None

    shot_only = dataset_service.get_datasets_for_device(
        "Device X", user=admin_user, scope=DatasetScope.SHOT
    )
    assert [ds.id for ds in shot_only] == [shot_ds.id]
    assert shot_only[0].shot_id == shot.id


def test_get_datasets_for_device_pages_without_repeats_or_gaps(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    """Paging a device listing larger than one page must cover it exactly once."""
    device_service.create(DeviceCreate(name="Device P", type="Type P"), user=admin_user)
    shot_service.create(
        ShotCreate(id="shot-p1", device_name="Device P"), user=admin_user
    )

    expected = set()
    for i in range(25):
        # Alternate device-level and shot-level so both are spread across pages.
        dataset = dataset_service.create(
            DatasetCreate(
                name=f"paged_{i:02d}",
                level=1,
                url=f"url_paged_{i}",
                device_name="Device P",
                shot_id="shot-p1" if i % 2 else None,
            ),
            user=admin_user,
        )
        expected.add(dataset.id)

    page_size = 10
    seen = []
    for offset in range(0, 30, page_size):
        page = dataset_service.get_datasets_for_device(
            "Device P", user=admin_user, offset=offset, limit=page_size
        )
        seen.extend(ds.id for ds in page)

    assert len(seen) == len(set(seen))
    assert set(seen) == expected


def test_create_global_dataset(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    dataset_create = DatasetCreate(
        name="reference_cross_sections", level=1, url="s3://global/xsec"
    )
    dataset = dataset_service.create(dataset_create, user=admin_user)
    assert dataset.device_name is None
    assert dataset.shot_id is None
    assert dataset.name == "reference_cross_sections"


def test_create_device_dataset(
    device_service: DeviceService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="NSTX", type="Spherical"), user=admin_user)
    dataset_create = DatasetCreate(
        name="machine_config", level=1, url="s3://nstx/config", device_name="NSTX"
    )
    dataset = dataset_service.create(dataset_create, user=admin_user)
    assert dataset.device_name == "NSTX"
    assert dataset.shot_id is None


def test_create_dataset_unauthorized_global(dataset_service: DatasetService):
    regular_user = AuthenticatedUser(id="user", scopes=())
    dataset_create = DatasetCreate(name="global", level=1, url="url")
    with pytest.raises(ForbiddenError):
        dataset_service.create(dataset_create, user=regular_user)


def test_create_dataset_unauthorized_device(
    device_service: DeviceService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="JET", type="Tokamak"), user=admin_user)
    regular_user = AuthenticatedUser(id="user", scopes=("mast_admin",))
    dataset_create = DatasetCreate(
        name="jet_data", level=1, url="url", device_name="JET"
    )
    with pytest.raises(ForbiddenError):
        dataset_service.create(dataset_create, user=regular_user)


def test_create_dataset_context_mismatch(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="MAST", type="Spherical"), user=admin_user)
    device_service.create(DeviceCreate(name="JET", type="Tokamak"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="mast-shot", device_name="MAST"), user=admin_user
    )

    dataset_create = DatasetCreate(
        name="bad_context", level=1, url="url", shot_id=shot.id, device_name="JET"
    )
    with pytest.raises(ResourceNotFoundError):
        dataset_service.create(dataset_create, user=admin_user)


def test_update_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    shot = shot_service.create(
        ShotCreate(id="shot-101", device_name="Test Device"), user=admin_user
    )
    assert shot.id == "shot-101"

    created_dataset = dataset_service.create(
        DatasetCreate(
            name="old_name",
            level=1,
            url="old_url",
            shot_id=shot.id,
            quality_flag="good",
            device_name="Test Device",
        ),
        user=admin_user,
    )
    assert created_dataset.id is not None
    assert created_dataset.quality_flag == "good"

    dataset_update = DatasetUpdate(name="new_name", level=2, quality_flag="bad")
    updated_dataset = dataset_service.update(
        id=created_dataset.id, obj_in=dataset_update, user=admin_user
    )

    assert updated_dataset.name == "new_name"
    assert updated_dataset.level == 2
    assert updated_dataset.quality_flag == "bad"
    assert updated_dataset.distributions[0].url == "old_url"  # Should remain unchanged


def test_delete_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    shot = shot_service.create(
        ShotCreate(id="shot-101", device_name="Test Device"), user=admin_user
    )
    assert shot.id == "shot-101"

    dataset_to_delete = dataset_service.create(
        DatasetCreate(
            name="to_delete",
            level=1,
            url="url_del",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )
    assert dataset_to_delete.id is not None

    dataset_service.delete(dataset_to_delete.id, user=admin_user)

    retrieved_dataset = dataset_service.get(dataset_to_delete.id)
    assert retrieved_dataset is None


def test_delete_dataset_not_found(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    with pytest.raises(ResourceNotFoundError):
        dataset_service.delete(999, user=admin_user)


def test_enrich_with_storage_options_s3(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
    mocker,
):
    """
    Verifies that datasets with an S3 storage protocol (`s3://`) successfully
    retrieve temporary STS credentials via `FileAccessService` and map them
    into the FSSpec `storage_options` dictionary required by Xarray/Zarr.
    """
    # Setup Data
    device_service.create(
        DeviceCreate(name="enrich-dev1", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="enrich-1", device_name="enrich-dev1"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_s3",
            level=1,
            url="s3://b/k1",
            shot_id=shot.id,
            device_name="enrich-dev1",
        ),
        user=admin_user,
    )

    mock_provider = mocker.MagicMock()
    mock_provider.generate_credentials.return_value = {
        "b": S3Credentials(
            access_key_id="mock_key",
            secret_access_key="mock_secret",
            session_token="mock_token",
            expiration=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
        )
    }

    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=mock_provider,
    )

    models = dataset_service.get_datasets_for_shot(
        shot.id, "enrich-dev1", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    opts = enriched[0].storage_options
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.key == "mock_key"
    assert opts.secret == "mock_secret"
    assert opts.token == "mock_token"


def test_enrich_with_storage_options_unsupported_protocol(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
    mocker,
):
    """
    Verifies that datasets utilizing alien or unsupported storage protocols (e.g., `local://`)
    gracefully fall back without crashing the catalog retrieval pipeline.
    Their `storage_options` should safely remain `None`.
    """
    # Setup Data
    device_service.create(
        DeviceCreate(name="enrich-dev2", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="enrich-2", device_name="enrich-dev2"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_none",
            level=1,
            url="local://not-s3",
            shot_id=shot.id,
            device_name="enrich-dev2",
        ),
        user=admin_user,
    )

    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=None,
    )

    models = dataset_service.get_datasets_for_shot(
        shot.id, "enrich-dev2", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    assert enriched[0].storage_options is None


def test_enrich_with_storage_options_url_absent_from_manifest(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
    mocker,
):
    """
    Verifies that datasets whose URL is absent from the manifest resource_map
    (e.g. provider could not obtain credentials) leave storage_options as None.
    """
    device_service.create(
        DeviceCreate(name="enrich-dev3", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="enrich-3", device_name="enrich-dev3"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_no_creds",
            level=1,
            url="s3://bucket/data",
            shot_id=shot.id,
            device_name="enrich-dev3",
        ),
        user=admin_user,
    )

    mocker.patch(
        "app.services.dataset_service.FileAccessService.generate_session_credentials",
        return_value=CredentialManifest(resource_map={}),
    )

    models = dataset_service.get_datasets_for_shot(
        shot.id, "enrich-dev3", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    assert enriched[0].storage_options is None


def test_enrich_with_storage_options_public_dataset_no_credentials(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
    mocker,
):
    """
    Verifies that public datasets receive anonymous storage options without
    minting STS credentials. The credential provider must never be called.
    """
    device_service.create(
        DeviceCreate(name="enrich-dev5", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="enrich-5", device_name="enrich-dev5"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_public_s3",
            level=1,
            url="s3://public-bucket/data",
            shot_id=shot.id,
            device_name="enrich-dev5",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )

    mock_provider = mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint"
    )

    models = dataset_service.get_datasets_for_shot(
        shot.id, "enrich-dev5", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    opts = enriched[0].storage_options
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.anon is True
    mock_provider.assert_not_called()


def test_create_dataset_non_s3_url_has_no_storage_options_type(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    """Distributions on non-S3 URLs (HTTPS, MDSplus, etc.) opt out of automated
    storage_options — the field stays ``None`` rather than getting a misleading
    fsspec_s3 default."""
    device_service.create(DeviceCreate(name="d-https", type="Test"), user=admin_user)
    shot_service.create(
        ShotCreate(id="s-https", device_name="d-https"), user=admin_user
    )

    ds = dataset_service.create(
        DatasetCreate(
            name="csv_https",
            level=1,
            url="https://example.org/data.csv",
            media_type="text/csv",
            shot_id="s-https",
            device_name="d-https",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )
    assert ds.distributions[0].storage_options_type is None

    models = dataset_service.get_datasets_for_shot(
        "s-https", "d-https", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)
    assert enriched[0].storage_options is None


def test_create_dataset_derives_icechunk_shape_from_media_type(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    """Omitting ``storage_options_type`` falls back to a media-type-driven
    default: icechunk media type → icechunk_s3 on the created Distribution."""
    device_service.create(DeviceCreate(name="d-derive", type="Test"), user=admin_user)
    shot_service.create(
        ShotCreate(id="s-derive", device_name="d-derive"), user=admin_user
    )

    ds = dataset_service.create(
        DatasetCreate(
            name="ic_derived",
            level=2,
            url="s3://bucket/shots/s-derive/analysed/equilibrium",
            media_type="application/vnd.icechunk+zarr",
            shot_id="s-derive",
            device_name="d-derive",
        ),
        user=admin_user,
    )
    assert ds.distributions[0].storage_options_type is StorageOptionsType.ICECHUNK_S3


def test_enrich_with_storage_options_icechunk_shape(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    """A distribution registered with ``storage_options_type=icechunk_s3``
    yields ``IcechunkS3StorageOptions`` (not the default fsspec shape).
    """
    device_service.create(DeviceCreate(name="ic-dev", type="Test"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="ic-shot", device_name="ic-dev"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_icechunk",
            level=2,
            url="s3://bucket/shots/ic-shot/analysed/equilibrium",
            endpoint_url="http://localhost:9000",
            storage_options_type=StorageOptionsType.ICECHUNK_S3,
            shot_id=shot.id,
            device_name="ic-dev",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )

    models = dataset_service.get_datasets_for_shot(shot.id, "ic-dev", user=admin_user)
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    opts = enriched[0].storage_options
    assert isinstance(opts, IcechunkS3StorageOptions)
    assert opts.endpoint_url == "http://localhost:9000"
    assert opts.anonymous is True
    assert opts.allow_http is True
    assert opts.force_path_style is True


def test_enrich_with_storage_options_distribution_region_override(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
    mocker,
):
    """When a distribution carries an explicit ``region``, the rendered
    storage_options uses that value rather than the provider config default.
    """
    from app.core.config import S3StorageProvider

    mocker.patch(
        "app.services.dataset_service.config.STORAGE_PROVIDERS",
        [
            S3StorageProvider(
                endpoint_url="http://localhost:9000",
                region="us-east-1",
                sts_role_arn="arn:test",
            )
        ],
    )

    device_service.create(DeviceCreate(name="region-dev", type="Test"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="region-shot", device_name="region-dev"), user=admin_user
    )

    dataset_service.create(
        DatasetCreate(
            name="ds_eu",
            level=1,
            url="s3://eu-bucket/data",
            endpoint_url="http://localhost:9000",
            region="eu-west-2",
            shot_id=shot.id,
            device_name="region-dev",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )

    models = dataset_service.get_datasets_for_shot(
        shot.id, "region-dev", user=admin_user
    )
    read_models = [dataset_service.to_read_model(m) for m in models]
    enriched = dataset_service.enrich_with_storage_options(read_models, admin_user)

    assert len(enriched) == 1
    opts = enriched[0].storage_options
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.client_kwargs is not None
    assert opts.client_kwargs["region_name"] == "eu-west-2"
