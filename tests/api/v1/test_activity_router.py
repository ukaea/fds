import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService
from tests.conftest import resource


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

    resp = test_client.patch(
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


@pytest.mark.parametrize(
    "path",
    [
        "/v1/activities/{id}",
        "/v1/activities/{id}/inputs",
        "/v1/activities/{id}/instruments",
        "/v1/activities/{id}/agents",
        "/v1/activities/{id}/delegations",
        "/activities/{id}",
    ],
)
def test_run_of_a_restricted_dataset_is_not_public(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    path: str,
):
    """Reading a run directly answers 403, as reading it through its dataset does."""
    DeviceService(session).create(
        DeviceCreate(name="sec-device", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    run = ActivityService(session).create(
        ActivityCreate(
            activity_type=ActivityType.SIMULATION, parameters={"confidential": "run"}
        ),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="sec-output",
            level=1,
            device_name="sec-device",
            access_level=AccessLevel.RESTRICTED,
            activity_id=run.id,
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get(path.format(id=run.id))
    assert response.status_code == 403, response.text
    assert "confidential" not in response.text


def test_run_of_a_public_dataset_is_public(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="pub-device", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    run = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.SIMULATION), user=admin_user
    )
    DatasetService(session).create(
        DatasetCreate(
            name="pub-output", level=1, device_name="pub-device", activity_id=run.id
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get(f"/v1/activities/{run.id}")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == run.id


def test_run_bundled_by_a_public_collection_is_public(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    run = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.SIMULATION), user=admin_user
    )
    CollectionService(session).create(
        CollectionCreate(
            name="pub-bundle", access_level=AccessLevel.PUBLIC, activity_id=run.id
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get(f"/v1/activities/{run.id}")
    assert response.status_code == 200, response.text


def test_run_with_no_outputs_is_not_public(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    run = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.SIMULATION), user=admin_user
    )
    session.commit()

    response = test_client.get(f"/v1/activities/{run.id}")
    assert response.status_code == 403, response.text


def test_device_admin_reads_a_run_through_a_restricted_output(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    mast_admin_user_token: dict,
    log_lines,
):
    """The read is recorded as a restricted read of the run."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    run = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.SIMULATION), user=admin_user
    )
    DatasetService(session).create(
        DatasetCreate(
            name="mast-output",
            level=1,
            device_name="MAST",
            access_level=AccessLevel.RESTRICTED,
            activity_id=run.id,
        ),
        user=admin_user,
    )
    session.commit()
    log_lines()

    response = test_client.get(
        f"/v1/activities/{run.id}", headers=mast_admin_user_token
    )
    assert response.status_code == 200, response.text
    (line,) = [
        entry
        for entry in log_lines()
        if entry.get("logger") == "fds.audit" and entry["event"] == "request"
    ]
    assert line["restricted_read"] == {"activity": [run.id]}


def test_run_json_ld_leaves_out_inputs_the_caller_cannot_read(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="ld-device", type="Test", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    datasets = DatasetService(session)
    open_input = datasets.create(
        DatasetCreate(name="open-input", level=1, device_name="ld-device"),
        user=admin_user,
    )
    restricted_input = datasets.create(
        DatasetCreate(
            name="restricted-input",
            level=1,
            device_name="ld-device",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    run = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.SIMULATION), user=admin_user
    )
    assert run.id is not None
    assert open_input.id is not None
    assert restricted_input.id is not None
    for input_id in (open_input.id, restricted_input.id):
        ActivityService(session).add_input(
            activity_id=run.id, dataset_id=input_id, user=admin_user
        )
    output = datasets.create(
        DatasetCreate(
            name="ld-output", level=2, device_name="ld-device", activity_id=run.id
        ),
        user=admin_user,
    )
    session.commit()
    ld = {"accept": "application/ld+json"}

    run_document = test_client.get(f"/activities/{run.id}", headers=ld).json()
    output_document = resource(
        test_client.get(f"/v1/datasets/id/{output.id}", headers=ld).json()
    )

    for used in (
        run_document["prov:used"],
        output_document["prov:wasGeneratedBy"]["prov:used"],
    ):
        assert [entity["dct:title"] for entity in used] == ["open-input"]
