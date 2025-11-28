from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


def test_create_device(client: TestClient):
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
    assert device.id is not None
    
    data = response.json()
    assert data["name"] == "JET"
    assert data["id"] == device.id


def test_read_device_not_found(client: TestClient):
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

# Helper function for creating shots within device tests
def create_a_shot_for_device_test(client: TestClient, device_id: int, shot_number: int = 1):
    response = client.post(
        f"/api/v1/devices/{device_id}/shots/",
        json={"shot_number": shot_number, "device_id": device_id},
    )
    assert response.status_code == 201
    return response.json()


def test_read_device_include_shots(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device = device_service.create(DeviceCreate(name="Device with Shots", type="Tokamak"))
    device_id = device.id
    assert device_id is not None

    create_a_shot_for_device_test(client, device_id, 101)
    create_a_shot_for_device_test(client, device_id, 102)

    response = client.get(f"/api/v1/devices/{device_id}?include_shots=true")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Device with Shots"
    assert "shots" in data
    assert len(data["shots"]) == 2
    assert data["shots"][0]["shot_number"] == 101
    assert data["shots"][1]["shot_number"] == 102


def test_read_devices_include_shots(client: TestClient, session: Session):
    device_service = DeviceService(session)
    device1 = device_service.create(DeviceCreate(name="Device One", type="Tokamak"))
    device2 = device_service.create(DeviceCreate(name="Device Two", type="Stellarator"))
    assert device1.id is not None
    assert device2.id is not None

    create_a_shot_for_device_test(client, device1.id, 201)
    create_a_shot_for_device_test(client, device1.id, 202)
    create_a_shot_for_device_test(client, device2.id, 301)

    response = client.get("/api/v1/devices/?include_shots=true")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2

    # Assuming order by creation, device1 then device2
    assert data[0]["name"] == "Device One"
    assert "shots" in data[0]
    assert len(data[0]["shots"]) == 2
    assert data[0]["shots"][0]["shot_number"] == 201

    assert data[1]["name"] == "Device Two"
    assert "shots" in data[1]
    assert len(data[1]["shots"]) == 1
    assert data[1]["shots"][0]["shot_number"] == 301
