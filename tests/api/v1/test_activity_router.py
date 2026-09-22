import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


@pytest.fixture(name="source")
def source_fixture(session: Session, admin_user: AuthenticatedUser):
    return SourceService(session).create(
        SourceCreate(
            name="test-source", description="A test source", kind=SourceKind.SOFTWARE
        ),
        user=admin_user,
    )


@pytest.fixture(name="activity")
def activity_fixture(session: Session, source, admin_user: AuthenticatedUser):
    assert source.id is not None
    return ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type=ActivityType.SIMULATION),
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
        "/v1/activities/",
        json={"source_id": source.id, "activity_type": "simulation"},
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_id"] == source.id
    assert data["activity_type"] == "simulation"
    assert "id" in data


def test_create_activity_with_full_metadata(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/v1/activities/",
        json={
            "source_id": source.id,
            "activity_type": "measurement",
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
        "/v1/activities/",
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
        "/v1/activities/",
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
        "/v1/activities/",
        json={"source_id": source.id, "activity_type": "simulation"},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.get(f"/v1/activities/{activity_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == activity_id


def test_get_activity_not_found(test_client: TestClient):
    resp = test_client.get("/v1/activities/9999")
    assert resp.status_code == 404


def test_update_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    create_resp = test_client.post(
        "/v1/activities/",
        json={"source_id": source.id, "activity_type": "measurement"},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.put(
        f"/v1/activities/{activity_id}",
        json={"activity_type": "simulation", "source_version": "v3.0"},
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["activity_type"] == "simulation"
    assert data["source_version"] == "v3.0"


def test_delete_activity(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    create_resp = test_client.post(
        "/v1/activities/",
        json={"source_id": source.id},
        headers=admin_user_token,
    )
    activity_id = create_resp.json()["id"]

    resp = test_client.delete(f"/v1/activities/{activity_id}", headers=admin_user_token)
    assert resp.status_code == 204

    resp = test_client.get(f"/v1/activities/{activity_id}")
    assert resp.status_code == 404


def test_create_activity_with_inline_inputs(
    test_client: TestClient,
    source,
    dataset,
    admin_user_token: dict[str, str],
):
    """An Activity declares its used inputs in the create request."""
    resp = test_client.post(
        "/v1/activities/",
        json={
            "source_id": source.id,
            "activity_type": "simulation",
            "inputs": [dataset.id],
        },
        headers=admin_user_token,
    )
    assert resp.status_code == 201


def test_create_activity_invalid_input_rejected(
    test_client: TestClient,
    source,
    admin_user_token: dict[str, str],
):
    resp = test_client.post(
        "/v1/activities/",
        json={"source_id": source.id, "inputs": [9999]},
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_activity_input_endpoints(
    test_client: TestClient,
    activity,
    dataset,
    admin_user_token: dict[str, str],
):
    base = f"/v1/activities/{activity.id}/inputs"
    created = test_client.post(f"{base}/{dataset.id}", headers=admin_user_token)
    assert created.status_code == 201
    assert created.json() == {"activity_id": activity.id, "dataset_id": dataset.id}
    listed = test_client.get(base, headers=admin_user_token)
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [dataset.id]
    assert (
        test_client.delete(f"{base}/{dataset.id}", headers=admin_user_token).status_code
        == 204
    )
    assert test_client.get(base, headers=admin_user_token).json() == []


def test_activity_instrument_endpoints(
    test_client: TestClient,
    activity,
    admin_user_token: dict[str, str],
):
    instrument = test_client.post(
        "/v1/sources/",
        json={"name": "probe", "kind": "instrument"},
        headers=admin_user_token,
    ).json()
    base = f"/v1/activities/{activity.id}/instruments"
    created = test_client.post(f"{base}/{instrument['id']}", headers=admin_user_token)
    assert created.status_code == 201
    assert created.json() == {
        "activity_id": activity.id,
        "source_id": instrument["id"],
    }
    assert [
        s["id"] for s in test_client.get(base, headers=admin_user_token).json()
    ] == [instrument["id"]]
    assert (
        test_client.delete(
            f"{base}/{instrument['id']}", headers=admin_user_token
        ).status_code
        == 204
    )


def test_activity_agent_endpoints(
    test_client: TestClient,
    activity,
    admin_user_token: dict[str, str],
):
    agent = test_client.post(
        "/v1/sources/",
        json={"name": "scheduler-x", "kind": "software"},
        headers=admin_user_token,
    ).json()
    base = f"/v1/activities/{activity.id}/agents"
    created = test_client.post(
        f"{base}/{agent['id']}",
        params={"role": "orchestrator"},
        headers=admin_user_token,
    )
    assert created.status_code == 201
    assert created.json() == {
        "activity_id": activity.id,
        "source_id": agent["id"],
        "role": "orchestrator",
    }
    assert test_client.get(base, headers=admin_user_token).json() == [
        {"activity_id": activity.id, "source_id": agent["id"], "role": "orchestrator"}
    ]
    assert (
        test_client.delete(
            f"{base}/{agent['id']}", headers=admin_user_token
        ).status_code
        == 204
    )


def test_activity_delegation_endpoints(
    test_client: TestClient,
    activity,
    source,
    admin_user_token: dict[str, str],
):
    scheduler = test_client.post(
        "/v1/sources/",
        json={"name": "scheduler-y", "kind": "software"},
        headers=admin_user_token,
    ).json()
    # The scheduler must be an agent of the run before it can be delegated to.
    test_client.post(
        f"/v1/activities/{activity.id}/agents/{scheduler['id']}",
        params={"role": "orchestrator"},
        headers=admin_user_token,
    )
    base = f"/v1/activities/{activity.id}/delegations"
    # The executor (source) acted on behalf of the scheduler.
    created = test_client.post(
        f"{base}/{source.id}/{scheduler['id']}",
        headers=admin_user_token,
    )
    assert created.status_code == 201
    assert created.json() == {
        "activity_id": activity.id,
        "subordinate_source_id": source.id,
        "responsible_source_id": scheduler["id"],
    }
    assert test_client.get(base, headers=admin_user_token).json() == [
        {
            "activity_id": activity.id,
            "subordinate_source_id": source.id,
            "responsible_source_id": scheduler["id"],
        }
    ]
    assert (
        test_client.delete(
            f"{base}/{source.id}/{scheduler['id']}", headers=admin_user_token
        ).status_code
        == 204
    )
