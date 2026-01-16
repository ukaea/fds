import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.shot import Shot, ShotCreate
from app.services.device_service import DeviceService
from app.services.exceptions import DeviceNotFoundError, ForbiddenError
from app.services.shot_service import ShotService


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


def test_create_shot_with_device_id(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    # Using global admin
    shot_create = ShotCreate(id="shot-101", device_name="Test Device")
    shot = shot_service.create(shot_create, admin_user)
    assert shot is not None
    assert shot.id == "shot-101"
    assert shot.device_id == device.id


def test_create_shot_with_device_scope(
    device_service: DeviceService,
    shot_service: ShotService,
    mast_admin_user: AuthenticatedUser,
    admin_user: AuthenticatedUser,
):
    # Device name matches scope "mast_admin"
    device_service.create(DeviceCreate(name="MAST", type="Test"), user=admin_user)

    shot_create = ShotCreate(id="mast-shot", device_name="MAST")
    shot = shot_service.create(shot_create, mast_admin_user)
    assert shot.id == "mast-shot"


def test_create_shot_unauthorized(
    device_service: DeviceService,
    shot_service: ShotService,
    mast_admin_user: AuthenticatedUser,
    admin_user: AuthenticatedUser,
):
    # User has mast_admin but trying to create for JET
    device_service.create(DeviceCreate(name="JET", type="Test"), user=admin_user)

    shot_create = ShotCreate(id="jet-shot", device_name="JET")
    with pytest.raises(ForbiddenError):
        shot_service.create(shot_create, mast_admin_user)


def test_create_shot_for_nonexistent_device(
    shot_service: ShotService, admin_user: AuthenticatedUser
):
    shot_create = ShotCreate(id="shot-102", device_name="Nonexistent")
    with pytest.raises(DeviceNotFoundError):
        shot_service.create(shot_create, admin_user)


def test_get_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    created_shot = shot_service.create(
        ShotCreate(id="shot-201", device_name="Test Device"), admin_user
    )
    assert created_shot is not None

    retrieved_shot = shot_service.get(created_shot.id)
    assert retrieved_shot is not None
    assert retrieved_shot.id == "shot-201"


def test_get_shots_for_device(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device1 = device_service.create(
        DeviceCreate(name="Device 1", type="A"), user=admin_user
    )
    _device2 = device_service.create(
        DeviceCreate(name="Device 2", type="B"), user=admin_user
    )

    shot_service.create(ShotCreate(id="shot-1001", device_name="Device 1"), admin_user)
    shot_service.create(ShotCreate(id="shot-1002", device_name="Device 1"), admin_user)
    shot_service.create(ShotCreate(id="shot-2001", device_name="Device 2"), admin_user)

    # Get shots for device 1
    device1_shots = shot_service.get_multi_by_device(device1.id)
    assert len(device1_shots) == 2
    assert all(shot.device_id == device1.id for shot in device1_shots)
    assert {shot.id for shot in device1_shots} == {"shot-1001", "shot-1002"}


def test_delete_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    session: Session,
    admin_user: AuthenticatedUser,
):
    _device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )

    shot_to_delete = shot_service.create(
        ShotCreate(id="shot-301", device_name="Test Device"), admin_user
    )
    assert shot_to_delete is not None

    shot_service.delete_with_auth(shot_to_delete.id, admin_user)

    db_shot = session.get(Shot, shot_to_delete.id)
    assert db_shot is None
