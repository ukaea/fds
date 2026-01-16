from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.services.device_service import DeviceService

# Dummy admin user for test setup
admin_user = AuthenticatedUser(id="test-admin", scopes=["fds-admin"])


def test_create_device(test_client: TestClient, admin_user_token: dict[str, str]):
    """Test that creating a device succeeds for a user with admin scope."""
    response = test_client.post(
        "/api/v1/devices/",
        headers=admin_user_token,
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "MAST-U"


def test_update_device(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(
        DeviceCreate(name="Initial", type="Test"), user=admin_user
    )
    response = test_client.put(
        f"/api/v1/devices/{device.name}",
        headers=admin_user_token,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


def test_delete_device(
    test_client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(
        DeviceCreate(name="ToDelete", type="Test"), user=admin_user
    )
    response = test_client.delete(
        f"/api/v1/devices/{device.name}", headers=admin_user_token
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Verify the device is actually deleted
    response = test_client.get(
        f"/api/v1/devices/{device.name}", headers=admin_user_token
    )
    assert response.status_code == 404


def test_delete_device_not_found(
    test_client: TestClient, admin_user_token: dict[str, str]
):
    response = test_client.delete(
        "/api/v1/devices/NonExistent", headers=admin_user_token
    )
    assert response.status_code == 404


def test_read_devices(test_client: TestClient, session: Session):
    # For read tests, we need to create data first, which requires admin privileges
    DeviceService(session).create(
        DeviceCreate(name="Device 1", type="Type A"), user=admin_user
    )
    DeviceService(session).create(
        DeviceCreate(name="Device 2", type="Type B"), user=admin_user
    )

    response = test_client.get("/api/v1/devices/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Device 1"
    assert data[1]["name"] == "Device 2"


def test_read_device(test_client: TestClient, session: Session):
    device = DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )

    response = test_client.get(f"/api/v1/devices/{device.name}")
    assert response.status_code == 200
    assert device.id is not None

    data = response.json()
    assert data["name"] == "JET"
    assert data["type"] == "Tokamak"


def test_read_device_not_found(test_client: TestClient):
    response = test_client.get("/api/v1/devices/NonExistent")
    assert response.status_code == 404
