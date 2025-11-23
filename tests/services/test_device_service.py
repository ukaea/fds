from sqlmodel import Session

from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.services.device_service import DeviceService


def test_create_device(session: Session):
    service = DeviceService(session)
    device_create = DeviceCreate(name="MAST", type="Tokamak", began_operations="2000-01-01", status="Retired")
    device = service.create_device(device_create)
    assert device.id is not None
    assert device.name == "MAST"
    assert device.type == "Tokamak"
    assert device.began_operations == "2000-01-01"
    assert device.status == "Retired"

    db_device = session.get(Device, device.id)
    assert db_device is not None
    assert db_device.name == "MAST"


def test_get_device(session: Session):
    service = DeviceService(session)
    device_create = DeviceCreate(name="JET", type="Tokamak")
    created_device = service.create_device(device_create)
    assert created_device.id is not None
    
    retrieved_device = service.get_device(created_device.id)
    assert retrieved_device is not None
    assert retrieved_device.id == created_device.id
    assert retrieved_device.name == "JET"


def test_get_device_not_found(session: Session):
    service = DeviceService(session)
    retrieved_device = service.get_device(999)  # Non-existent ID
    assert retrieved_device is None


def test_get_devices(session: Session):
    service = DeviceService(session)
    device1 = service.create_device(DeviceCreate(name="Device A", type="Type X"))
    device2 = service.create_device(DeviceCreate(name="Device B", type="Type Y"))

    devices = service.get_devices()
    assert len(devices) == 2
    assert device1 in devices
    assert device2 in devices


def test_get_devices_with_limit_and_offset(session: Session):
    service = DeviceService(session)
    for i in range(10):
        service.create_device(DeviceCreate(name=f"Device {i}", type="Type A"))

    # Test limit
    devices_limited = service.get_devices(limit=5)
    assert len(devices_limited) == 5

    # Test offset
    devices_offset = service.get_devices(offset=5, limit=5)
    assert len(devices_offset) == 5
    assert devices_offset[0].name == "Device 5"


def test_update_device(session: Session):
    service = DeviceService(session)
    device_create = DeviceCreate(name="Update Test", type="Initial", status="Initial Status")
    created_device = service.create_device(device_create)
    assert created_device.id is not None
    
    device_update = DeviceUpdate(name="Updated Test", status="Updated Status")
    updated_device = service.update_device(created_device.id, device_update)
    assert updated_device is not None
    assert updated_device.name == "Updated Test"
    assert updated_device.type == "Initial"
    assert updated_device.status == "Updated Status"

    db_device = session.get(Device, created_device.id)
    assert db_device is not None
    assert db_device.name == "Updated Test"


def test_update_device_not_found(session: Session):
    service = DeviceService(session)
    device_update = DeviceUpdate(name="Non Existent")
    updated_device = service.update_device(999, device_update)
    assert updated_device is None


def test_delete_device(session: Session):
    service = DeviceService(session)
    device_create = DeviceCreate(name="Delete Me", type="Temp")
    created_device = service.create_device(device_create)
    assert created_device.id is not None
    
    result = service.delete_device(created_device.id)
    assert result is True

    db_device = session.get(Device, created_device.id)
    assert db_device is None


def test_delete_device_not_found(session: Session):
    service = DeviceService(session)
    result = service.delete_device(999)
    assert result is False
