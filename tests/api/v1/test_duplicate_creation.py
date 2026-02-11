from fastapi.testclient import TestClient
from sqlmodel import Session


def test_duplicate_device_creation(
    test_client: TestClient, admin_user_token: dict[str, str]
):
    """
    Test that creating a duplicate device returns 409 Conflict.
    """
    device_data = {
        "name": "duplicate-device-1",
        "description": "Test device for duplication",
        "type": "tokamak",
    }

    # First creation - should succeed
    response = test_client.post(
        "/api/v1/devices/",
        headers=admin_user_token,
        json=device_data,
    )
    assert response.status_code == 201

    # Second creation - should fail with 409
    response = test_client.post(
        "/api/v1/devices/",
        headers=admin_user_token,
        json=device_data,
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_duplicate_shot_creation(
    test_client: TestClient, admin_user_token: dict[str, str], session: Session
):
    """
    Test that creating a duplicate shot returns 409 Conflict.
    """
    # Ensure device exists
    from app.models.device import Device

    device = Device(name="duplicate-shot-device", description="Test", type="tokamak")
    session.add(device)
    session.commit()

    shot_data = {"id": "1000", "device_name": "duplicate-shot-device"}

    # First creation
    response = test_client.post(
        "/api/v1/devices/duplicate-shot-device/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 201

    # Second creation
    response = test_client.post(
        "/api/v1/devices/duplicate-shot-device/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_duplicate_dataset_creation(
    test_client: TestClient, admin_user_token: dict[str, str], session: Session
):
    """
    Test that creating a duplicate dataset returns 409 Conflict.
    """
    # Setup context
    from app.models.device import Device
    from app.models.shot import Shot

    device = Device(name="dup-ds-device", description="Test", type="tokamak")
    session.add(device)
    session.commit()
    session.refresh(device)

    shot = Shot(id="2000", device_id=device.id)
    session.add(shot)
    session.commit()

    dataset_data = {
        "name": "dup-dataset",
        "data_url": "s3://test/dup",
        "access_level": "public",
        "level": 1,
    }

    # First creation
    response = test_client.post(
        "/api/v1/devices/dup-ds-device/shots/2000/datasets",
        headers=admin_user_token,
        json=dataset_data,
    )
    assert response.status_code == 201

    # Second creation
    response = test_client.post(
        "/api/v1/devices/dup-ds-device/shots/2000/datasets",
        headers=admin_user_token,
        json=dataset_data,
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
