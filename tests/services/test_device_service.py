from sqlmodel import Session

from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.services.device_service import DeviceService
from app.auth.security import AuthenticatedUser


def test_create_device(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device_create = DeviceCreate(
        name="MAST", type="Tokamak", began_operations="2000-01-01", status="Retired"
    )
    device = service.create(device_create, user=admin_user)
    assert device.id is not None
    assert device.name == "MAST"
    assert device.type == "Tokamak"
    assert device.began_operations == "2000-01-01"
    assert device.status == "Retired"

    db_device = session.get(Device, device.id)
    assert db_device is not None
    assert db_device.name == "MAST"


def test_get_device(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device_create = DeviceCreate(name="JET", type="Tokamak")
    created_device = service.create(device_create, user=admin_user)
    assert created_device.id is not None

    retrieved_device = service.get(created_device.id)
    assert retrieved_device is not None
    assert retrieved_device.id == created_device.id
    assert retrieved_device.name == "JET"


def test_get_device_not_found(session: Session):
    service = DeviceService(session)
    retrieved_device = service.get(999)  # Non-existent ID
    assert retrieved_device is None


def test_get_devices(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device1 = service.create(
        DeviceCreate(name="Device A", type="Type X"), user=admin_user
    )
    device2 = service.create(
        DeviceCreate(name="Device B", type="Type Y"), user=admin_user
    )

    devices = service.get_multi()
    assert len(devices) == 2
    assert device1 in devices
    assert device2 in devices


def test_get_devices_with_limit_and_offset(
    session: Session, admin_user: AuthenticatedUser
):
    service = DeviceService(session)
    for i in range(10):
        service.create(DeviceCreate(name=f"Device {i}", type="Type A"), user=admin_user)

    # Test limit
    devices_limited = service.get_multi(limit=5)
    assert len(devices_limited) == 5

    # Test offset
    devices_offset = service.get_multi(offset=5, limit=5)
    assert len(devices_offset) == 5
    assert devices_offset[0].name == "Device 5"


def test_update_device(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device_create = DeviceCreate(
        name="Update Test", type="Initial", status="Initial Status"
    )
    created_device = service.create(device_create, user=admin_user)
    assert created_device.id is not None

    db_device_to_update = service.get(created_device.id)
    assert db_device_to_update is not None

    device_update = DeviceUpdate(name="Updated Test", status="Updated Status")
    updated_device = service.update(
        db_obj=db_device_to_update, obj_in=device_update, user=admin_user
    )
    assert updated_device is not None
    assert updated_device.name == "Updated Test"
    assert updated_device.type == "Initial"
    assert updated_device.status == "Updated Status"

    db_device = session.get(Device, created_device.id)
    assert db_device is not None
    assert db_device.name == "Updated Test"


def test_delete_device(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device_create = DeviceCreate(name="Delete Me", type="Temp")
    created_device = service.create(device_create, user=admin_user)
    assert created_device.id is not None

    device_deleted = service.delete(created_device.id, user=admin_user)
    assert device_deleted is True

    db_device = session.get(Device, created_device.id)
    assert db_device is None


def test_delete_device_not_found(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    device_deleted = service.delete(999, user=admin_user)
    assert device_deleted is False
