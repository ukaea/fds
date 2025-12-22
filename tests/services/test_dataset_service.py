import pytest
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.dataset import DatasetCreate, DatasetUpdate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.dataset_service import DatasetService
from app.auth.security import AuthenticatedUser
from app.services.exceptions import ResourceNotFoundError, ForbiddenError, ConflictError


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
    assert shot is not None
    assert shot.id == "shot-101"

    dataset_create = DatasetCreate(
        name="core_profiles",
        level=2,
        data_url="s3://test-bucket/shot-101/core_profiles.zarr",
        quality_flag="good",
        shot_id=shot.id,
    )
    dataset = dataset_service.create(dataset_create, user=admin_user)

    assert dataset is not None
    assert dataset.id is not None
    assert dataset.name == "core_profiles"
    assert dataset.level == 2
    assert dataset.data_url == "s3://test-bucket/shot-101/core_profiles.zarr"
    assert dataset.quality_flag == "good"
    assert dataset.shot_id == shot.id


def test_create_dataset_for_nonexistent_shot(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    dataset_create = DatasetCreate(
        name="nonexistent_data",
        level=1,
        data_url="s3://nonexistent",
        shot_id="nonexistent-shot",
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
    assert shot is not None
    assert shot.id == "shot-101"

    created_dataset = dataset_service.create(
        DatasetCreate(name="mag_diag", level=1, data_url="s3://url", shot_id=shot.id),
        user=admin_user,
    )
    assert created_dataset is not None

    retrieved_dataset = dataset_service.get(created_dataset.id)
    assert retrieved_dataset is not None
    assert retrieved_dataset.id == created_dataset.id
    assert retrieved_dataset.name == "mag_diag"


def test_get_dataset_not_found(dataset_service: DatasetService):
    retrieved_dataset = dataset_service.get(999)
    assert retrieved_dataset is None


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
    assert shot is not None
    assert shot.id == "shot-101"

    dataset_service.create(
        DatasetCreate(name="data1", level=1, data_url="url1", shot_id=shot.id),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(name="data2", level=2, data_url="url2", shot_id=shot.id),
        user=admin_user,
    )

    datasets = dataset_service.get_multi()
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
    assert shot1 is not None
    assert shot1.id == "shot-1"

    device2 = device_service.create(
        DeviceCreate(name="Device 2", type="Type B"), user=admin_user
    )
    assert device2.id is not None
    shot2 = shot_service.create(
        ShotCreate(id="shot-2", device_name="Device 2"), user=admin_user
    )
    assert shot2 is not None
    assert shot2.id == "shot-2"

    dataset_service.create(
        DatasetCreate(
            name="shot1_data1", level=1, data_url="url_s1_d1", shot_id=shot1.id
        ),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(
            name="shot1_data2", level=2, data_url="url_s1_d2", shot_id=shot1.id
        ),
        user=admin_user,
    )
    dataset_service.create(
        DatasetCreate(
            name="shot2_data1", level=1, data_url="url_s2_d1", shot_id=shot2.id
        ),
        user=admin_user,
    )

    datasets_shot1 = dataset_service.get_datasets_for_shot(shot1.id)
    assert len(datasets_shot1) == 2
    assert all(ds.shot_id == shot1.id for ds in datasets_shot1)

    datasets_shot2 = dataset_service.get_datasets_for_shot(shot2.id)
    assert len(datasets_shot2) == 1
    assert all(ds.shot_id == shot2.id for ds in datasets_shot2)


def test_create_global_dataset(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    dataset_create = DatasetCreate(
        name="reference_cross_sections", level=1, data_url="s3://global/xsec"
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
        name="machine_config", level=1, data_url="s3://nstx/config", device_name="NSTX"
    )
    dataset = dataset_service.create(dataset_create, user=admin_user)
    assert dataset.device_name == "NSTX"
    assert dataset.shot_id is None


def test_create_dataset_unauthorized_global(dataset_service: DatasetService):
    regular_user = AuthenticatedUser(id="user", scopes=[])
    dataset_create = DatasetCreate(name="global", level=1, data_url="url")
    with pytest.raises(ForbiddenError):
        dataset_service.create(dataset_create, user=regular_user)


def test_create_dataset_unauthorized_device(
    device_service: DeviceService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="JET", type="Tokamak"), user=admin_user)
    regular_user = AuthenticatedUser(id="user", scopes=["mast_admin"])
    dataset_create = DatasetCreate(
        name="jet_data", level=1, data_url="url", device_name="JET"
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
        name="bad_context", level=1, data_url="url", shot_id=shot.id, device_name="JET"
    )
    with pytest.raises(ConflictError):
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
    assert shot is not None
    assert shot.id == "shot-101"

    created_dataset = dataset_service.create(
        DatasetCreate(
            name="old_name",
            level=1,
            data_url="old_url",
            shot_id=shot.id,
            quality_flag="good",
        ),
        user=admin_user,
    )
    assert created_dataset is not None
    assert created_dataset.id is not None
    assert created_dataset.quality_flag == "good"

    db_dataset_to_update = dataset_service.get(created_dataset.id)
    assert db_dataset_to_update is not None

    dataset_update = DatasetUpdate(name="new_name", level=2, quality_flag="bad")
    updated_dataset = dataset_service.update(
        db_obj=db_dataset_to_update, obj_in=dataset_update, user=admin_user
    )

    assert updated_dataset is not None
    assert updated_dataset.name == "new_name"
    assert updated_dataset.level == 2
    assert updated_dataset.quality_flag == "bad"
    assert updated_dataset.data_url == "old_url"  # Should remain unchanged


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
    assert shot is not None
    assert shot.id == "shot-101"

    dataset_to_delete = dataset_service.create(
        DatasetCreate(name="to_delete", level=1, data_url="url_del", shot_id=shot.id),
        user=admin_user,
    )
    assert dataset_to_delete is not None

    dataset_service.delete_with_auth(dataset_to_delete.id, user=admin_user)

    retrieved_dataset = dataset_service.get(dataset_to_delete.id)
    assert retrieved_dataset is None


def test_delete_dataset_not_found(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    with pytest.raises(ResourceNotFoundError):
        dataset_service.delete_with_auth(999, user=admin_user)
