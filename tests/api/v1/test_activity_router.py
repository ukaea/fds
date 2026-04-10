import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


@pytest.fixture(name="source")
def source_fixture(session: Session, admin_user: AuthenticatedUser):
    return SourceService(session).create(
        SourceCreate(name="test-source", description="A test source"), user=admin_user
    )


@pytest.fixture(name="activity")
def activity_fixture(session: Session, source, admin_user: AuthenticatedUser):
    assert source.id is not None
    return ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type="SIMULATION"),
        user=admin_user,
    )


@pytest.fixture(name="dataset")
def dataset_fixture(session: Session, admin_user: AuthenticatedUser):
    DeviceService(session).create(
        DeviceCreate(name="inp-device", type="Test"), user=admin_user
    )
    shot = ShotService(session).create(
        ShotCreate(id="inp-shot", device_name="inp-device"), user=admin_user
    )
    return DatasetService(session).create(
        DatasetCreate(
            name="inp-dataset",
            level=0,
            url="s3://inp",
            shot_id=shot.id,
            device_name="inp-device",
        ),
        user=admin_user,
    )


def test_create_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": source.id, "activity_type": "SIMULATION"},
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_id"] == source.id
    assert data["activity_type"] == "SIMULATION"
    assert "id" in data


def test_create_activity_with_full_metadata(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/api/v1/activities/",
        json={
            "source_id": source.id,
            "activity_type": "MEASUREMENT",
            "source_version": "v2.1",
            "parameters": {"sample_rate": 1000},
            "started_at": "2024-01-01T10:00:00",
            "ended_at": "2024-01-01T11:00:00",
        },
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_version"] == "v2.1"
    assert data["parameters"] == {"sample_rate": 1000}
    assert data["started_at"] is not None
    assert data["ended_at"] is not None


def test_create_activity_invalid_source(
    test_client: TestClient,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": 9999},
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_create_activity_non_admin_forbidden(
    test_client: TestClient,
    source,
    non_admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": source.id},
        headers=non_admin_user_token,
    )
    assert resp.status_code == 403


def test_get_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    create_resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": source.id, "activity_type": "SIMULATION"},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.get(f"/api/v1/activities/{activity_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == activity_id


def test_get_activity_not_found(test_client: TestClient):
    resp = test_client.get("/api/v1/activities/9999")
    assert resp.status_code == 404


def test_update_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    create_resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": source.id, "activity_type": "MEASUREMENT"},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.put(
        f"/api/v1/activities/{activity_id}",
        json={"activity_type": "SIMULATION", "source_version": "v3.0"},
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["activity_type"] == "SIMULATION"
    assert data["source_version"] == "v3.0"


def test_delete_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    create_resp = test_client.post(
        "/api/v1/activities/",
        json={"source_id": source.id},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.delete(
        f"/api/v1/activities/{activity_id}", headers=admin_user_token
    )
    assert resp.status_code == 204

    resp = test_client.get(f"/api/v1/activities/{activity_id}")
    assert resp.status_code == 404


def test_add_and_list_activity_inputs(
    test_client: TestClient,
    activity,
    dataset,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        f"/api/v1/activities/{activity.id}/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 201

    resp = test_client.get(
        f"/api/v1/activities/{activity.id}/inputs",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == dataset.id


def test_add_input_idempotent(
    test_client: TestClient,
    activity,
    dataset,
    admin_user_token: dict[str, str],
):
    """Adding the same input twice should not error."""
    test_client.post(
        f"/api/v1/activities/{activity.id}/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    resp = test_client.post(
        f"/api/v1/activities/{activity.id}/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 201


def test_remove_activity_input(
    test_client: TestClient,
    activity,
    dataset,
    admin_user_token: dict[str, str],
):
    test_client.post(
        f"/api/v1/activities/{activity.id}/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    resp = test_client.delete(
        f"/api/v1/activities/{activity.id}/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 204

    resp = test_client.get(
        f"/api/v1/activities/{activity.id}/inputs",
        headers=admin_user_token,
    )
    assert resp.json() == []


def test_remove_input_not_found(
    test_client: TestClient,
    activity,
    admin_user_token: dict[str, str],
):
    resp = test_client.delete(
        f"/api/v1/activities/{activity.id}/inputs/9999",
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_add_input_invalid_activity(
    test_client: TestClient,
    dataset,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        f"/api/v1/activities/9999/inputs/{dataset.id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_add_input_invalid_dataset(
    test_client: TestClient,
    activity,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        f"/api/v1/activities/{activity.id}/inputs/9999",
        headers=admin_user_token,
    )
    assert resp.status_code == 404
