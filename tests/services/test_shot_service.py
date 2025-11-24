import pytest
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.models.shot import Shot, ShotCreate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


def test_create_shot(device_service: DeviceService, shot_service: ShotService):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot_create = ShotCreate(shot_number=101, device_id=device.id)
    shot = shot_service.create(shot_create)
    assert shot is not None
    assert shot.id is not None
    assert shot.shot_number == 101
    assert shot.device_id == device.id


def test_create_shot_for_nonexistent_device(shot_service: ShotService):
    shot_create = ShotCreate(shot_number=102, device_id=999)  # Non-existent device
    with pytest.raises(ValueError):
        shot_service.create(shot_create)


def test_get_shot(device_service: DeviceService, shot_service: ShotService):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    created_shot = shot_service.create(ShotCreate(shot_number=201, device_id=device.id))
    assert created_shot is not None
    assert created_shot.id is not None

    retrieved_shot = shot_service.get(created_shot.id)
    assert retrieved_shot is not None
    assert retrieved_shot.id == created_shot.id
    assert retrieved_shot.shot_number == 201


def test_get_shots_for_device(device_service: DeviceService, shot_service: ShotService):
    device1 = device_service.create(DeviceCreate(name="Device 1", type="A"))
    device2 = device_service.create(DeviceCreate(name="Device 2", type="B"))
    assert device1.id is not None
    assert device2.id is not None

    shot_service.create(ShotCreate(shot_number=1001, device_id=device1.id))
    shot_service.create(ShotCreate(shot_number=1002, device_id=device1.id))
    shot_service.create(ShotCreate(shot_number=2001, device_id=device2.id))

    # Get shots for device 1
    device1_shots = shot_service.get_shots_for_device(device1.id)
    assert len(device1_shots) == 2
    assert all(shot.device_id == device1.id for shot in device1_shots)
    assert {shot.shot_number for shot in device1_shots} == {1001, 1002}

    # Get shots for device 2
    device2_shots = shot_service.get_shots_for_device(device2.id)
    assert len(device2_shots) == 1
    assert device2_shots[0].device_id == device2.id
    assert device2_shots[0].shot_number == 2001


def test_delete_shot(
    device_service: DeviceService, shot_service: ShotService, session: Session
):
    device = device_service.create(DeviceCreate(name="Test Device", type="Test"))
    assert device.id is not None

    shot_to_delete = shot_service.create(
        ShotCreate(shot_number=301, device_id=device.id)
    )
    assert shot_to_delete is not None
    assert shot_to_delete.id is not None

    shot_service.delete(shot_to_delete.id)

    db_shot = session.get(Shot, shot_to_delete.id)
    assert db_shot is None
