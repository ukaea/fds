import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


@pytest.fixture(name="setup_linking_data")
def setup_linking_data_fixture(
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Instantiate services directly
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    dataset_service = DatasetService(session)
    source_service = SourceService(session)

    # Create Context
    device_service.create(
        DeviceCreate(name="LinkingDevice", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="100", device_name="LinkingDevice"), user=admin_user
    )

    # Create Dataset
    dataset = dataset_service.create(
        DatasetCreate(
            name="linked_data",
            level=1,
            data_url="s3://linked",
            shot_id=shot.id,
            device_name="LinkingDevice",
        ),
        user=admin_user,
    )

    # Create Source
    source = source_service.create(
        SourceCreate(name="sim_code_v1", description="Simulation Code"), user=admin_user
    )

    return dataset, source


def test_create_and_read_dataset_source_link(
    test_client: TestClient,
    setup_linking_data,
    admin_user_token: dict[str, str],
):
    dataset, source = setup_linking_data

    # 1. Create Link
    link_data = {
        "dataset_id": dataset.id,
        "source_id": source.id,
        "activity_type": "SIMULATION",
        "source_version": "v1.0",
        "parameters": {"param_a": 123},
    }

    resp = test_client.post(
        f"/api/v1/datasets/{dataset.id}/sources",
        json=link_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["dataset_id"] == dataset.id
    assert data["source_id"] == source.id
    assert data["activity_type"] == "SIMULATION"
    assert data["parameters"]["param_a"] == 123

    # 2. Read Links
    resp = test_client.get(
        f"/api/v1/datasets/{dataset.id}/sources",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_id"] == source.id

    # 3. Delete Link
    resp = test_client.delete(
        f"/api/v1/datasets/{dataset.id}/sources/{source.id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 204

    # 4. Verify Deletion
    resp = test_client.get(
        f"/api/v1/datasets/{dataset.id}/sources",
        headers=admin_user_token,
    )


def test_create_link_without_dataset_id_in_body(
    test_client: TestClient,
    setup_linking_data,
    admin_user_token: dict[str, str],
):
    """
    Test creating a link where dataset_id is NOT provided in the body (implied from URL).
    """
    dataset, source = setup_linking_data

    # Payload without dataset_id
    link_data = {
        "source_id": source.id,
        "activity_type": "CALIBRATION",
        "source_version": "v2.0",
        "parameters": {"voltage": 500},
    }

    resp = test_client.post(
        f"/api/v1/datasets/{dataset.id}/sources",
        json=link_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["dataset_id"] == dataset.id
    assert data["source_id"] == source.id
    assert data["activity_type"] == "CALIBRATION"
