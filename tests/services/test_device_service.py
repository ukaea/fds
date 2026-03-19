import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.models.policy import AccessLevel
from app.services.device_service import DeviceService
from app.services.exceptions import DeviceNotFoundError, FDSValidationError

IDP_A = "https://idp-a.example.com"


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


def test_get_device_by_name(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    service.create(DeviceCreate(name="JET", type="Tokamak"), user=admin_user)

    retrieved = service.get_by_name("JET", admin_user)
    assert retrieved.name == "JET"


def test_get_device_by_name_not_found(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    with pytest.raises(DeviceNotFoundError):
        service.get_by_name("NonExistent", admin_user)


def test_get_id_disabled(session: Session):
    service = DeviceService(session)
    with pytest.raises(NotImplementedError):
        service.get(1)


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

    device_update = DeviceUpdate(name="Updated Test", status="Updated Status")
    updated_device = service.update(
        device_name="Update Test", obj_in=device_update, user=admin_user
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

    device_deleted = service.delete(created_device.name, user=admin_user)
    assert device_deleted is True

    db_device = session.get(Device, created_device.id)
    assert db_device is None


def test_delete_device_not_found(session: Session, admin_user: AuthenticatedUser):
    service = DeviceService(session)
    with pytest.raises(DeviceNotFoundError):
        service.delete("NonExistent", user=admin_user)


@pytest.mark.usefixtures("idp_config")
def test_create_device_public_with_required_scopes_rejected(
    session: Session, admin_user: AuthenticatedUser
):
    service = DeviceService(session)
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        service.create(
            DeviceCreate(
                name="bad",
                access_level=AccessLevel.PUBLIC,
                required_scopes=["some:scope"],
            ),
            user=admin_user,
        )


@pytest.mark.usefixtures("idp_config")
def test_create_device_null_access_with_allowed_idps_rejected(
    session: Session, admin_user: AuthenticatedUser
):
    service = DeviceService(session)
    with pytest.raises(FDSValidationError, match="allowed_idps requires"):
        service.create(
            DeviceCreate(name="bad", allowed_idps=[IDP_A]),
            user=admin_user,
        )


@pytest.mark.usefixtures("idp_config")
def test_create_device_restricted_with_policy_accepted(
    session: Session, admin_user: AuthenticatedUser
):
    service = DeviceService(session)
    device = service.create(
        DeviceCreate(
            name="gated",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["lab:read"],
            allowed_idps=[IDP_A],
        ),
        user=admin_user,
    )
    assert device.id is not None
    assert device.required_scopes == ["lab:read"]
    assert device.allowed_idps == [IDP_A]


@pytest.mark.usefixtures("idp_config")
def test_update_device_transition_to_public_with_scopes_rejected(
    session: Session, admin_user: AuthenticatedUser
):
    service = DeviceService(session)
    device = service.create(
        DeviceCreate(
            name="upgrading",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["some:scope"],
        ),
        user=admin_user,
    )
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        service.update(
            device_name=device.name,
            obj_in=DeviceUpdate(access_level=AccessLevel.PUBLIC),
            user=admin_user,
        )
