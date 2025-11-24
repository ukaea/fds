from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


def test_create_device(client: TestClient, session: Session):
    response = client.post(
        "/api/v1/devices/",
        json={"name": "MAST-U", "type": "Tokamak", "status": "Operational"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "MAST-U"
    assert data["type"] == "Tokamak"
    assert data["status"] == "Operational"
    assert "id" in data


def test_read_devices(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device_service.create(DeviceCreate(name="Device 1", type="Type A"))
    device_service.create(DeviceCreate(name="Device 2", type="Type B"))

    response = client.get("/api/v1/devices/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Device 1"
    assert data[1]["name"] == "Device 2"


def test_read_device(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device = device_service.create(DeviceCreate(name="JET", type="Tokamak"))

    response = client.get(f"/api/v1/devices/{device.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "JET"
    assert data["id"] == device.id


def test_read_device_not_found(client: TestClient, session: Session):
    response = client.get("/api/v1/devices/999")
    assert response.status_code == 404


def test_update_device(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device = device_service.create(DeviceCreate(name="Initial Name", type="Test"))

    response = client.put(
        f"/api/v1/devices/{device.id}",
        json={"name": "Updated Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["type"] == "Test"
    assert data["id"] == device.id


def test_delete_device(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device = device_service.create(DeviceCreate(name="ToDelete", type="Test"))

    response = client.delete(f"/api/v1/devices/{device.id}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    response = client.get(f"/api/v1/devices/{device.id}")
    assert response.status_code == 404


def test_delete_device_not_found(client: TestClient):
    response = client.delete("/api/v1/devices/999")
    assert response.status_code == 404
