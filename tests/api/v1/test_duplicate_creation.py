from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.device import Device
from app.models.shot import Shot
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.source_service import SourceService


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


def test_duplicate_dataset_name_allowed_with_different_activities(
    test_client: TestClient, admin_user_token: dict[str, str], session: Session
):
    """
    Two datasets with the same name in the same context are permitted when
    attributed to different Activities (ADR-0028) — e.g. two JINTRAC runs
    both producing an 'equilibrium' IDS on the same shot.
    """
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    device = Device(name="dup-ds-device", description="Test", type="tokamak")
    session.add(device)
    session.commit()

    shot = Shot(id="2000", device_name=device.name)
    session.add(shot)
    session.commit()

    source = SourceService(session).create(
        SourceCreate(name="dup-source", kind=SourceKind.SOFTWARE), user=admin
    )
    assert source.id is not None
    activity1 = ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type=ActivityType.SIMULATION),
        user=admin,
    )
    activity2 = ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type=ActivityType.MEASUREMENT),
        user=admin,
    )

    response1 = test_client.post(
        "/api/v1/devices/dup-ds-device/shots/2000/datasets",
        headers=admin_user_token,
        json={
            "name": "equilibrium",
            "url": "s3://run1/eq",
            "level": 1,
            "activity_id": activity1.id,
        },
    )
    assert response1.status_code == 201

    response2 = test_client.post(
        "/api/v1/devices/dup-ds-device/shots/2000/datasets",
        headers=admin_user_token,
        json={
            "name": "equilibrium",
            "url": "s3://run2/eq",
            "level": 1,
            "activity_id": activity2.id,
        },
    )
    assert response2.status_code == 201
    assert response1.json()["id"] != response2.json()["id"]


def test_duplicate_dataset_name_rejected_without_activity(
    test_client: TestClient, admin_user_token: dict[str, str], session: Session
):
    """
    Two unattributed datasets with the same name in the same context conflict.
    """
    device = Device(name="dup-ds-device-2", description="Test", type="tokamak")
    session.add(device)
    session.commit()

    shot = Shot(id="2001", device_name=device.name)
    session.add(shot)
    session.commit()

    dataset_data = {"name": "raw", "url": "s3://test/raw", "level": 0}

    response1 = test_client.post(
        "/api/v1/devices/dup-ds-device-2/shots/2001/datasets",
        headers=admin_user_token,
        json=dataset_data,
    )
    assert response1.status_code == 201

    response2 = test_client.post(
        "/api/v1/devices/dup-ds-device-2/shots/2001/datasets",
        headers=admin_user_token,
        json=dataset_data,
    )
    assert response2.status_code == 409
