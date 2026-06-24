import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


@pytest.fixture(name="setup")
def setup_fixture(session: Session, admin_user: AuthenticatedUser):
    DeviceService(session).create(
        DeviceCreate(name="act-device", type="Test"), user=admin_user
    )
    shot = ShotService(session).create(
        ShotCreate(id="s1", device_name="act-device"), user=admin_user
    )
    source = SourceService(session).create(
        SourceCreate(name="act-source", description="Test source"), user=admin_user
    )
    assert source.id is not None
    activity = ActivityService(session).create(
        ActivityCreate(
            source_id=source.id,
            activity_type=ActivityType.SIMULATION,
            source_version="v1.0",
            parameters={"key": "val"},
        ),
        user=admin_user,
    )
    dataset_with_activity = DatasetService(session).create(
        DatasetCreate(
            name="ds-with-activity",
            level=1,
            url="s3://test/ds",
            shot_id=shot.id,
            device_name="act-device",
            activity_id=activity.id,
        ),
        user=admin_user,
    )
    dataset_no_activity = DatasetService(session).create(
        DatasetCreate(
            name="ds-no-activity",
            level=1,
            url="s3://test/ds2",
            shot_id=shot.id,
            device_name="act-device",
        ),
        user=admin_user,
    )
    return dataset_with_activity, dataset_no_activity, activity, source


def test_get_dataset_activity(
    test_client: TestClient,
    setup,
    admin_user_token: dict[str, str],
):
    dataset, _, activity, _ = setup
    resp = test_client.get(
        f"/api/v1/datasets/{dataset.id}/activity",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == activity.id
    assert data["activity_type"] == "simulation"
    assert data["source_version"] == "v1.0"
    assert data["parameters"] == {"key": "val"}


def test_get_dataset_activity_no_activity(
    test_client: TestClient,
    setup,
    admin_user_token: dict[str, str],
):
    _, dataset_no_activity, _, _ = setup
    resp = test_client.get(
        f"/api/v1/datasets/{dataset_no_activity.id}/activity",
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_get_dataset_activity_dataset_not_found(
    test_client: TestClient,
    admin_user_token: dict[str, str],
):
    resp = test_client.get("/api/v1/datasets/9999/activity", headers=admin_user_token)
    assert resp.status_code == 404


def test_get_dataset_source(
    test_client: TestClient,
    setup,
    admin_user_token: dict[str, str],
):
    dataset, _, _, source = setup
    resp = test_client.get(
        f"/api/v1/datasets/{dataset.id}/source",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == source.id
    assert data["name"] == "act-source"
    assert data["description"] == "Test source"


def test_get_dataset_source_no_activity(
    test_client: TestClient,
    setup,
    admin_user_token: dict[str, str],
):
    _, dataset_no_activity, _, _ = setup
    resp = test_client.get(
        f"/api/v1/datasets/{dataset_no_activity.id}/source",
        headers=admin_user_token,
    )
    assert resp.status_code == 404


def test_get_dataset_source_dataset_not_found(
    test_client: TestClient,
    admin_user_token: dict[str, str],
):
    resp = test_client.get("/api/v1/datasets/9999/source", headers=admin_user_token)
    assert resp.status_code == 404
