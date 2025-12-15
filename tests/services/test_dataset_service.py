import pytest
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.dataset import DatasetCreate, DatasetUpdate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.dataset_service import DatasetService


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
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot = shot_service.create(ShotCreate(shot_number=101, device_id=device.id))
    assert shot is not None
    assert shot.id is not None

    dataset_create = DatasetCreate(
        name="core_profiles",
        level=2,
        data_url="s3://test-bucket/shot-101/core_profiles.zarr",
        quality_flag="good",
        shot_id=shot.id,
    )
    dataset = dataset_service.create(dataset_create)

    assert dataset is not None
    assert dataset.id is not None
    assert dataset.name == "core_profiles"
    assert dataset.level == 2
    assert dataset.data_url == "s3://test-bucket/shot-101/core_profiles.zarr"
    assert dataset.quality_flag == "good"
    assert dataset.shot_id == shot.id


def test_create_dataset_for_nonexistent_shot(dataset_service: DatasetService):
    dataset_create = DatasetCreate(
        name="nonexistent_data", level=1, data_url="s3://nonexistent", shot_id=999
    )
    with pytest.raises(ValueError):
        dataset_service.create(dataset_create)


def test_get_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot = shot_service.create(ShotCreate(shot_number=101, device_id=device.id))
    assert shot is not None
    assert shot.id is not None

    created_dataset = dataset_service.create(
        DatasetCreate(name="mag_diag", level=1, data_url="s3://url", shot_id=shot.id)
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
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot = shot_service.create(ShotCreate(shot_number=101, device_id=device.id))
    assert shot is not None
    assert shot.id is not None

    dataset_service.create(
        DatasetCreate(name="data1", level=1, data_url="url1", shot_id=shot.id)
    )
    dataset_service.create(
        DatasetCreate(name="data2", level=2, data_url="url2", shot_id=shot.id)
    )

    datasets = dataset_service.get_multi()
    assert len(datasets) == 2


def test_get_datasets_for_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
):
    device1 = device_service.create(DeviceCreate(name="Device 1", type="Type A"))
    assert device1.id is not None
    shot1 = shot_service.create(ShotCreate(shot_number=1, device_id=device1.id))
    assert shot1 is not None
    assert shot1.id is not None

    device2 = device_service.create(DeviceCreate(name="Device 2", type="Type B"))
    assert device2.id is not None
    shot2 = shot_service.create(ShotCreate(shot_number=2, device_id=device2.id))
    assert shot2 is not None
    assert shot2.id is not None

    dataset_service.create(
        DatasetCreate(
            name="shot1_data1", level=1, data_url="url_s1_d1", shot_id=shot1.id
        )
    )
    dataset_service.create(
        DatasetCreate(
            name="shot1_data2", level=2, data_url="url_s1_d2", shot_id=shot1.id
        )
    )
    dataset_service.create(
        DatasetCreate(
            name="shot2_data1", level=1, data_url="url_s2_d1", shot_id=shot2.id
        )
    )

    datasets_shot1 = dataset_service.get_datasets_for_shot(shot1.id)
    assert len(datasets_shot1) == 2
    assert all(ds.shot_id == shot1.id for ds in datasets_shot1)

    datasets_shot2 = dataset_service.get_datasets_for_shot(shot2.id)
    assert len(datasets_shot2) == 1
    assert all(ds.shot_id == shot2.id for ds in datasets_shot2)


def test_update_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot = shot_service.create(ShotCreate(shot_number=101, device_id=device.id))
    assert shot is not None
    assert shot.id is not None

    created_dataset = dataset_service.create(
        DatasetCreate(
            name="old_name",
            level=1,
            data_url="old_url",
            shot_id=shot.id,
            quality_flag="good",
        )
    )
    assert created_dataset is not None
    assert created_dataset.quality_flag == "good"

    dataset_update = DatasetUpdate(name="new_name", level=2, quality_flag="bad")
    updated_dataset = dataset_service.update(created_dataset.id, dataset_update)

    assert updated_dataset is not None
    assert updated_dataset.name == "new_name"
    assert updated_dataset.level == 2
    assert updated_dataset.quality_flag == "bad"
    assert updated_dataset.data_url == "old_url"  # Should remain unchanged


def test_update_dataset_not_found(dataset_service: DatasetService):
    dataset_update = DatasetUpdate(name="new_name")
    updated_dataset = dataset_service.update(999, dataset_update)
    assert updated_dataset is None


def test_delete_dataset(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot = shot_service.create(ShotCreate(shot_number=101, device_id=device.id))
    assert shot is not None
    assert shot.id is not None

    dataset_to_delete = dataset_service.create(
        DatasetCreate(name="to_delete", level=1, data_url="url_del", shot_id=shot.id)
    )
    assert dataset_to_delete is not None

    dataset_service.delete(dataset_to_delete.id)

    retrieved_dataset = dataset_service.get(dataset_to_delete.id)
    assert retrieved_dataset is None


def test_delete_dataset_not_found(dataset_service: DatasetService):
    deleted_dataset = dataset_service.delete(999)
    assert deleted_dataset is False
