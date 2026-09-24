from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.models.source import SourceCreate, SourceKind
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService

# Dummy admin user for test setup
admin_user = AuthenticatedUser(id="test-admin", scopes=("fds-admin",))


def test_create_device(test_client: TestClient, admin_user_token: dict[str, str]):
    """Test that creating a device succeeds for a user with admin scope."""
    response = test_client.post(
        "/v1/devices/",
        headers=admin_user_token,
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "mast-u"


def test_update_device(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(
        DeviceCreate(name="Initial", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    response = test_client.put(
        f"/v1/devices/{device.name}",
        headers=admin_user_token,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "updated name"


def test_delete_device(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(
        DeviceCreate(name="ToDelete", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    response = test_client.delete(
        f"/v1/devices/{device.name}", headers=admin_user_token
    )
    assert response.status_code == 204
    assert response.content == b""

    # Verify the device is actually deleted
    response = test_client.get(f"/v1/devices/{device.name}", headers=admin_user_token)
    assert response.status_code == 404


def test_delete_device_holding_shots_is_refused(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    """Deleting a device must not quietly take its shots and datasets with it."""
    device = DeviceService(session).create(
        DeviceCreate(name="Occupied", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    ShotService(session).create(
        ShotCreate(id="1", device_name=device.name), user=admin_user
    )

    response = test_client.delete(
        f"/v1/devices/{device.name}", headers=admin_user_token
    )

    assert response.status_code == 409
    assert "1 shot" in response.json()["detail"]
    assert (
        test_client.get(
            f"/v1/devices/{device.name}", headers=admin_user_token
        ).status_code
        == 200
    )


def test_delete_device_holding_sources_is_refused(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(
        DeviceCreate(name="HasSources", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    SourceService(session).create(
        SourceCreate(name="efit", kind=SourceKind.SOFTWARE, device_name=device.name),
        user=admin_user,
    )

    response = test_client.delete(
        f"/v1/devices/{device.name}", headers=admin_user_token
    )

    assert response.status_code == 409
    assert "1 source" in response.json()["detail"]


def test_delete_device_not_found(
    test_client: TestClient, admin_user_token: dict[str, str]
):
    response = test_client.delete("/v1/devices/NonExistent", headers=admin_user_token)
    assert response.status_code == 404


def test_read_devices(test_client: TestClient, session: Session):
    # For read tests, we need to create data first, which requires admin privileges
    DeviceService(session).create(
        DeviceCreate(name="Device 1", type="Type A", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DeviceService(session).create(
        DeviceCreate(name="Device 2", type="Type B", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )

    response = test_client.get("/v1/devices/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "device 1"
    assert data[1]["name"] == "device 2"


def test_read_device(test_client: TestClient, session: Session):
    device = DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )

    response = test_client.get(f"/v1/devices/{device.name}")
    assert response.status_code == 200
    assert device.id is not None

    data = response.json()
    assert data["name"] == "jet"
    assert data["type"] == "Tokamak"


def test_device_lookup_is_case_insensitive(test_client: TestClient, session: Session):
    """A device registered as "MAST" resolves through any casing of its name."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    ShotService(session).create(
        ShotCreate(id="30420", device_name="MAST", access_level=AccessLevel.PUBLIC),
        admin_user,
    )

    upper = test_client.get("/v1/devices/MAST")
    lower = test_client.get("/v1/devices/mast")
    assert upper.status_code == 200
    assert upper.json() == lower.json()
    assert upper.json()["name"] == "mast"

    # Nested resources resolve through either casing of the device segment.
    for name in ("MAST", "mast"):
        response = test_client.get(f"/v1/devices/{name}/shots/30420")
        assert response.status_code == 200
        assert response.json()["device_name"] == "mast"


def test_read_device_not_found(test_client: TestClient):
    response = test_client.get("/v1/devices/NonExistent")
    assert response.status_code == 404


def test_read_restricted_device_requires_auth(
    test_client: TestClient, session: Session
):
    DeviceService(session).create(
        DeviceCreate(
            name="Restricted Device",
            type="Tokamak",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )

    response = test_client.get("/v1/devices/Restricted Device")
    assert response.status_code == 403


def test_read_devices_filters_restricted_for_anonymous(
    test_client: TestClient, session: Session
):
    DeviceService(session).create(
        DeviceCreate(
            name="Public Device", type="Type A", access_level=AccessLevel.PUBLIC
        ),
        user=admin_user,
    )
    DeviceService(session).create(
        DeviceCreate(
            name="Private Device", type="Type B", access_level=AccessLevel.RESTRICTED
        ),
        user=admin_user,
    )

    response = test_client.get("/v1/devices/")
    assert response.status_code == 200

    names = [device["name"] for device in response.json()]
    assert "public device" in names
    assert "private device" not in names
