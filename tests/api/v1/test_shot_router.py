from fastapi.testclient import TestClient
from sqlmodel import Session


def create_a_device(
    client: TestClient, name: str = "Test Device", device_type: str = "Tokamak"
):
    response = client.post(
        "/api/v1/devices/",
        json={"name": name, "type": device_type, "status": "Operational"},
    )
    assert response.status_code == 200
    return response.json()


def create_a_shot(client: TestClient, device_id: int, shot_number: int = 1):
    response = client.post(
        f"/api/v1/devices/{device_id}/shots/",
        json={"shot_number": shot_number, "device_id": device_id},
    )
    assert response.status_code == 201
    return response.json()


def test_create_shot(client: TestClient):
    device = create_a_device(client)
    device_id = device["id"]

    response = client.post(
        f"/api/v1/devices/{device_id}/shots/",
        json={"shot_number": 1, "device_id": device_id},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["shot_number"] == 1
    assert data["device_id"] == device_id
    assert "id" in data


def test_create_shot_device_not_found(client: TestClient):
    response = client.post(
        "/api/v1/devices/999/shots/",
        json={"shot_number": 1, "device_id": 999},
    )
    assert response.status_code == 404


def test_create_shot_mismatched_device_id(client: TestClient):
    device1 = create_a_device(client, name="Device1")
    device2 = create_a_device(client, name="Device2")
    device1_id = device1["id"]
    device2_id = device2["id"]

    response = client.post(
        f"/api/v1/devices/{device1_id}/shots/",
        json={"shot_number": 1, "device_id": device2_id},  # Mismatched device_id
    )
    assert response.status_code == 400


def test_read_shots(client: TestClient, session: Session):
    device = create_a_device(client)
    device_id = device["id"]
    create_a_shot(client, device_id, 1)
    create_a_shot(client, device_id, 2)

    response = client.get(f"/api/v1/devices/{device_id}/shots/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["shot_number"] == 1
    assert data[1]["shot_number"] == 2


def test_read_shots_device_not_found(client: TestClient):
    response = client.get("/api/v1/devices/999/shots/")
    assert response.status_code == 404


def test_read_shot(client: TestClient, session: Session):
    device = create_a_device(client)
    device_id = device["id"]
    shot = create_a_shot(client, device_id, 100)
    shot_id = shot["id"]

    response = client.get(f"/api/v1/devices/{device_id}/shots/{shot_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["shot_number"] == 100
    assert data["id"] == shot_id
    assert data["device_id"] == device_id


def test_read_shot_not_found(client: TestClient):
    device = create_a_device(client)
    device_id = device["id"]
    response = client.get(f"/api/v1/devices/{device_id}/shots/999")
    assert response.status_code == 404


def test_read_shot_wrong_device(client: TestClient):
    device1 = create_a_device(client, name="Device1")
    device2 = create_a_device(client, name="Device2")
    device1_id = device1["id"]
    device2_id = device2["id"]
    shot = create_a_shot(client, device1_id, 1)

    # Try to access shot from device1 via device2's endpoint
    response = client.get(f"/api/v1/devices/{device2_id}/shots/{shot['id']}")
    assert response.status_code == 404


def test_update_shot(client: TestClient, session: Session):
    device = create_a_device(client)
    device_id = device["id"]
    shot = create_a_shot(client, device_id, 1)
    shot_id = shot["id"]

    response = client.put(
        f"/api/v1/devices/{device_id}/shots/{shot_id}",
        json={"shot_number": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["shot_number"] == 2
    assert data["id"] == shot_id


def test_update_shot_not_found(client: TestClient):
    device = create_a_device(client)
    device_id = device["id"]
    response = client.put(
        f"/api/v1/devices/{device_id}/shots/999",
        json={"shot_number": 2},
    )
    assert response.status_code == 404


def test_update_shot_wrong_device(client: TestClient):
    device1 = create_a_device(client, name="Device1")
    device2 = create_a_device(client, name="Device2")
    device1_id = device1["id"]
    device2_id = device2["id"]
    shot = create_a_shot(client, device1_id, 1)

    response = client.put(
        f"/api/v1/devices/{device2_id}/shots/{shot['id']}",  # Wrong device_id in path
        json={"shot_number": 2},
    )
    assert response.status_code == 404


def test_delete_shot(client: TestClient, session: Session):
    device = create_a_device(client)
    device_id = device["id"]
    shot = create_a_shot(client, device_id, 1)
    shot_id = shot["id"]

    response = client.delete(f"/api/v1/devices/{device_id}/shots/{shot_id}")
    assert response.status_code == 204  # No Content

    response = client.get(f"/api/v1/devices/{device_id}/shots/{shot_id}")
    assert response.status_code == 404


def test_delete_shot_not_found(client: TestClient):
    device = create_a_device(client)
    device_id = device["id"]
    response = client.delete(f"/api/v1/devices/{device_id}/shots/999")
    assert response.status_code == 404


def test_delete_shot_wrong_device(client: TestClient):
    device1 = create_a_device(client, name="Device1")
    device2 = create_a_device(client, name="Device2")
    device1_id = device1["id"]
    shot = create_a_shot(client, device1_id, 1)

    response = client.delete(f"/api/v1/devices/{device2['id']}/shots/{shot['id']}")
    assert response.status_code == 404


# Tests for include_device parameter
def test_read_shot_include_device(client: TestClient, session: Session):
    device = create_a_device(client, name="Included Device")
    device_id = device["id"]
    shot = create_a_shot(client, device_id, 500)
    shot_id = shot["id"]

    response = client.get(
        f"/api/v1/devices/{device_id}/shots/{shot_id}?include_device=true"
    )
    assert response.status_code == 200

    data = response.json()
    assert data["shot_number"] == 500
    assert data["id"] == shot_id
    assert "device" in data
    assert data["device"]["name"] == "Included Device"
    assert data["device"]["id"] == device_id


def test_read_shots_include_device(client: TestClient):
    device = create_a_device(client, name="Bulk Device")
    device_id = device["id"]
    create_a_shot(client, device_id, 10)
    create_a_shot(client, device_id, 11)

    response = client.get(f"/api/v1/devices/{device_id}/shots/?include_device=true")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert "device" in data[0]
    assert data[0]["device"]["name"] == "Bulk Device"
    assert data[0]["device"]["id"] == device_id
    assert "device" in data[1]
    assert data[1]["device"]["name"] == "Bulk Device"
    assert data[1]["device"]["id"] == device_id
