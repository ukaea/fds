import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.distribution import DistributionCreate
from app.models.policy import AccessLevel
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.distribution_service import DistributionService
from app.services.source_service import SourceService


@pytest.fixture(name="restricted_dataset_id")
def restricted_dataset_id_fixture(
    session: Session, admin_user: AuthenticatedUser
) -> int:
    """A RESTRICTED dataset carrying an activity, a source and a distribution."""
    DeviceService(session).create(
        DeviceCreate(name="sub-device", type="Tokamak"), user=admin_user
    )
    source = SourceService(session).create(
        SourceCreate(
            name="sub-source", description="Producing code", kind=SourceKind.SOFTWARE
        ),
        user=admin_user,
    )
    assert source.id is not None
    activity = ActivityService(session).create(
        ActivityCreate(
            source_id=source.id,
            activity_type=ActivityType.SIMULATION,
            source_version="v1.0",
            parameters={"confidential": "run parameter"},
        ),
        user=admin_user,
    )
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="secret",
            level=1,
            device_name="sub-device",
            access_level=AccessLevel.RESTRICTED,
            activity_id=activity.id,
        ),
        user=admin_user,
    )
    assert dataset.id is not None
    DistributionService(session).create(
        dataset.id,
        DistributionCreate(url="s3://bucket/secret.nc", format="NetCDF-4"),
        user=admin_user,
    )
    session.commit()
    return dataset.id


@pytest.mark.parametrize("sub_resource", ["distributions", "activity", "source"])
def test_restricted_dataset_sub_resources_are_not_public(
    test_client: TestClient, restricted_dataset_id: int, sub_resource: str
):
    """Each sub-resource answers 403, matching the dataset's own endpoint."""
    assert (
        test_client.get(f"/api/v1/datasets/id/{restricted_dataset_id}").status_code
        == 403
    )

    resp = test_client.get(
        f"/api/v1/datasets/{restricted_dataset_id}/{sub_resource}",
    )
    assert resp.status_code == 403, resp.text


def test_restricted_distribution_url_does_not_leak(
    test_client: TestClient, restricted_dataset_id: int
):
    """The object-store location is the most damaging of the three leaks, so
    assert on the body as well as the status."""
    resp = test_client.get(f"/api/v1/datasets/{restricted_dataset_id}/distributions")
    assert "s3://bucket/secret.nc" not in resp.text


def test_restricted_activity_parameters_do_not_leak(
    test_client: TestClient, restricted_dataset_id: int
):
    """Run parameters are free-form JSON and may carry anything the producer put
    there, so they must not appear in a refused response."""
    resp = test_client.get(f"/api/v1/datasets/{restricted_dataset_id}/activity")
    assert "confidential" not in resp.text


@pytest.mark.parametrize("sub_resource", ["distributions", "activity", "source"])
def test_admin_can_still_read_sub_resources(
    test_client: TestClient,
    restricted_dataset_id: int,
    admin_user_token: dict[str, str],
    sub_resource: str,
):
    """The fix must not close the endpoints to callers who are entitled to them."""
    resp = test_client.get(
        f"/api/v1/datasets/{restricted_dataset_id}/{sub_resource}",
        headers=admin_user_token,
    )
    assert resp.status_code == 200, resp.text


def test_public_dataset_sub_resources_stay_anonymous(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """Anonymous reads of a PUBLIC dataset must keep working."""
    dataset = DatasetService(session).create(
        DatasetCreate(name="open", level=1, access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    assert dataset.id is not None
    DistributionService(session).create(
        dataset.id,
        DistributionCreate(url="s3://bucket/open.nc", format="NetCDF-4"),
        user=admin_user,
    )
    session.commit()

    resp = test_client.get(f"/api/v1/datasets/{dataset.id}/distributions")
    assert resp.status_code == 200, resp.text
    assert [d["url"] for d in resp.json()] == ["s3://bucket/open.nc"]


def test_missing_dataset_still_404s(test_client: TestClient, admin_user_token: dict):
    """Enforcement is added ahead of the existence check for activity, so confirm
    a genuinely absent dataset is still reported as missing, not forbidden."""
    resp = test_client.get(
        "/api/v1/datasets/999999/distributions", headers=admin_user_token
    )
    assert resp.status_code == 404, resp.text
