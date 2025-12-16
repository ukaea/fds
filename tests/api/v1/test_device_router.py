from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


# --- Authorization Tests for POST /devices/ ---

def test_create_device_fails_no_token(client: TestClient):
    """Test that creating a device fails with 403 if no token is provided."""
    response = client.post(
        "/api/v1/devices/",
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    # The HTTPBearer scheme returns 403 if the header is missing
    assert response.status_code == 401


def test_create_device_fails_non_admin(
    client: TestClient, non_admin_user_token: dict[str, str]
):
    """Test that creating a device fails with 403 for a user without admin scope."""
    response = client.post(
        "/api/v1/devices/",
        headers=non_admin_user_token,
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    assert response.status_code == 403


def test_create_device_succeeds_admin(
    client: TestClient, admin_user_token: dict[str, str]
):
    """Test that creating a device succeeds for a user with admin scope."""
    response = client.post(
        "/api/v1/devices/",
        headers=admin_user_token,
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "MAST-U"


# --- Authorization Tests for PUT /devices/{device_id} ---

def test_update_device_fails_no_token(client: TestClient, session: Session):
    device = DeviceService(session).create(DeviceCreate(name="Initial", type="Test"))
    response = client.put(f"/api/v1/devices/{device.name}", json={"name": "Updated"})
    assert response.status_code == 401


def test_update_device_fails_non_admin(
    client: TestClient, session: Session, non_admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(DeviceCreate(name="Initial", type="Test"))
    response = client.put(
        f"/api/v1/devices/{device.name}",
        headers=non_admin_user_token,
        json={"name": "Updated"},
    )
    assert response.status_code == 403


def test_update_device_succeeds_admin(
    client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(DeviceCreate(name="Initial", type="Test"))
    response = client.put(
        f"/api/v1/devices/{device.name}",
        headers=admin_user_token,
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


# --- Authorization Tests for DELETE /devices/{device_id} ---

def test_delete_device_fails_no_token(client: TestClient, session: Session):
    device = DeviceService(session).create(DeviceCreate(name="ToDelete", type="Test"))
    response = client.delete(f"/api/v1/devices/{device.name}")
    assert response.status_code == 401


def test_delete_device_fails_non_admin(
    client: TestClient, session: Session, non_admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(DeviceCreate(name="ToDelete", type="Test"))
    response = client.delete(
        f"/api/v1/devices/{device.name}", headers=non_admin_user_token
    )
    assert response.status_code == 403


def test_delete_device_succeeds_admin(
    client: TestClient, session: Session, admin_user_token: dict[str, str]
):
    device = DeviceService(session).create(DeviceCreate(name="ToDelete", type="Test"))
    response = client.delete(f"/api/v1/devices/{device.name}", headers=admin_user_token)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Verify the device is actually deleted
    response = client.get(f"/api/v1/devices/{device.name}", headers=admin_user_token)
    assert response.status_code == 404


def test_delete_device_not_found(client: TestClient, admin_user_token: dict[str, str]):
    response = client.delete("/api/v1/devices/NonExistent", headers=admin_user_token)
    assert response.status_code == 404


# --- Existing Read-Only Tests (Unaffected by Auth) ---

def test_read_devices(client: TestClient, session: Session):
    # For read tests, we need to create data first, which requires admin privileges
    DeviceService(session).create(DeviceCreate(name="Device 1", type="Type A"))
    DeviceService(session).create(DeviceCreate(name="Device 2", type="Type B"))

    response = client.get("/api/v1/devices/")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Device 1"
    assert data[1]["name"] == "Device 2"


def test_read_device(client: TestClient, session: Session):
    device = DeviceService(session).create(DeviceCreate(name="JET", type="Tokamak"))

    response = client.get(f"/api/v1/devices/{device.name}")
    assert response.status_code == 200
    assert device.id is not None

    data = response.json()
    assert data["name"] == "JET"
    assert data["id"] == device.id


def test_read_device_not_found(client: TestClient):
    response = client.get("/api/v1/devices/NonExistent")
    assert response.status_code == 404