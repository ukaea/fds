from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate
from app.models.dataset import Dataset, DatasetCreate
from app.models.device import DeviceCreate
from app.models.file_access import S3Credentials
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.services.source_service import SourceService

# Dummy users for setup
admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))
mast_admin = AuthenticatedUser(id="mast", scopes=("mast_admin",))


def test_create_global_dataset(test_client: TestClient, admin_user_token: dict):
    response = test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "global_const", "level": 1, "url": "s3://global"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "global_const"
    assert "device_name" not in data
    assert "shot_id" not in data


def test_create_device_dataset(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="NSTX", type="Tokamak"), user=admin_user
    )
    session.commit()

    response = test_client.post(
        "/api/v1/devices/NSTX/datasets/",
        headers=admin_user_token,
        json={"name": "machine_params", "level": 1, "url": "s3://nstx"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "machine_params"
    assert data["device_name"] == "nstx"


def test_create_shot_dataset(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Spherical"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(id="123", device_name="MAST"), user=admin_user
    )
    session.commit()

    response = test_client.post(
        "/api/v1/devices/MAST/shots/123/datasets/",
        headers=admin_user_token,
        json={"name": "efit", "level": 2, "url": "s3://mast/123/efit"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "efit"
    assert data["device_name"] == "mast"
    assert data["shot_id"] == "123"


def test_read_dataset_by_name(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Spherical"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(id="456", device_name="MAST"), user=admin_user
    )
    session.commit()

    # Create via API
    test_client.post(
        "/api/v1/devices/MAST/shots/456/datasets/",
        headers=admin_user_token,
        json={"name": "plasma_current", "level": 1, "url": "s3://url"},
    )

    response = test_client.get("/api/v1/devices/MAST/shots/456/datasets/plasma_current")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "plasma_current"


def test_dataset_same_name_returns_list(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """Same name from different activities is allowed; GET by name returns all matches."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Spherical"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(id="789", device_name="MAST"), user=admin_user
    )
    source = SourceService(session).create(
        SourceCreate(name="list-src"), user=admin_user
    )
    assert source.id is not None
    act1 = ActivityService(session).create(
        ActivityCreate(source_id=source.id), user=admin_user
    )
    act2 = ActivityService(session).create(
        ActivityCreate(source_id=source.id), user=admin_user
    )
    session.commit()

    r1 = test_client.post(
        "/api/v1/devices/MAST/shots/789/datasets/",
        headers=admin_user_token,
        json={
            "name": "duplicate",
            "level": 1,
            "url": "s3://url/1",
            "activity_id": act1.id,
        },
    )
    r2 = test_client.post(
        "/api/v1/devices/MAST/shots/789/datasets/",
        headers=admin_user_token,
        json={
            "name": "duplicate",
            "level": 1,
            "url": "s3://url/2",
            "activity_id": act2.id,
        },
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]

    response = test_client.get(
        "/api/v1/devices/MAST/shots/789/datasets/duplicate",
        headers=admin_user_token,
    )
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_unauthorized_device_dataset(
    test_client: TestClient, session: Session, jet_admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Spherical"), user=admin_user
    )
    session.commit()

    # JET admin trying to create on MAST
    response = test_client.post(
        "/api/v1/devices/MAST/datasets/",
        headers=jet_admin_user_token,
        json={"name": "illegal", "level": 1, "url": "url"},
    )
    assert response.status_code == 403


def test_list_device_datasets(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="DIII-D", type="Tokamak"), user=admin_user
    )
    session.commit()

    test_client.post(
        "/api/v1/devices/DIII-D/datasets/",
        headers=admin_user_token,
        json={"name": "data_a", "level": 1, "url": "url_a"},
    )
    test_client.post(
        "/api/v1/devices/DIII-D/datasets/",
        headers=admin_user_token,
        json={"name": "data_b", "level": 1, "url": "url_b"},
    )

    response = test_client.get("/api/v1/devices/DIII-D/datasets/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_device_datasets_includes_shot_datasets(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="W7-X", type="Stellarator"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(id="200", device_name="W7-X"), user=admin_user
    )
    session.commit()

    test_client.post(
        "/api/v1/devices/W7-X/datasets/",
        headers=admin_user_token,
        json={"name": "coil_geometry", "level": 0, "url": "url_geom"},
    )
    test_client.post(
        "/api/v1/devices/W7-X/shots/200/datasets/",
        headers=admin_user_token,
        json={"name": "electron_density", "level": 1, "url": "url_ne"},
    )

    response = test_client.get("/api/v1/devices/W7-X/datasets/")
    assert response.status_code == 200
    assert {ds["name"] for ds in response.json()} == {
        "coil_geometry",
        "electron_density",
    }

    response = test_client.get("/api/v1/devices/W7-X/datasets/?scope=device")
    assert response.status_code == 200
    assert [ds["name"] for ds in response.json()] == ["coil_geometry"]

    response = test_client.get("/api/v1/devices/W7-X/datasets/?scope=shot")
    assert response.status_code == 200
    assert [ds["name"] for ds in response.json()] == ["electron_density"]

    response = test_client.get("/api/v1/devices/W7-X/datasets/?scope=nonsense")
    assert response.status_code == 422


def test_read_global_dataset_by_name(test_client: TestClient, admin_user_token: dict):
    test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "global_ref", "level": 1, "url": "url"},
    )

    response = test_client.get("/api/v1/datasets/global_ref")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "global_ref"


def test_update_dataset(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    # Create global via API
    test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "to_update", "level": 1, "url": "url"},
    )
    # Find ID from DB (since it's not in the Read model)
    dataset = session.exec(select(Dataset).where(Dataset.name == "to_update")).one()
    dataset_id = dataset.id

    response = test_client.patch(
        f"/api/v1/datasets/{dataset_id}",
        headers=admin_user_token,
        json={"level": 5},
    )
    assert response.status_code == 200
    assert response.json()["level"] == 5


def test_delete_dataset(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "to_delete", "level": 1, "url": "url"},
    )
    dataset = session.exec(select(Dataset).where(Dataset.name == "to_delete")).one()

    response = test_client.delete(
        f"/api/v1/datasets/{dataset.id}",
        headers=admin_user_token,
    )
    assert response.status_code == 204

    response = test_client.get("/api/v1/datasets/to_delete")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_dataset_unauthorized(
    test_client: TestClient,
    session: Session,
    jet_admin_user_token: dict,
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    DatasetService(session).create(
        DatasetCreate(
            name="restricted_delete",
            level=1,
            url="url",
            device_name="MAST",
        ),
        user=admin_user,
    )
    dataset = session.exec(
        select(Dataset).where(Dataset.name == "restricted_delete")
    ).one()

    response = test_client.delete(
        f"/api/v1/datasets/{dataset.id}",
        headers=jet_admin_user_token,
    )
    assert response.status_code == 403

    assert session.get(Dataset, dataset.id) is not None


def test_get_datasets_with_storage_options(
    test_client: TestClient, session: Session, admin_user_token: dict, mocker
):
    # Register device, shot, and dataset
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    DeviceService(session).create(DeviceCreate(name="OPTS", type="Tokamak"), user=admin)
    ShotService(session).create(ShotCreate(id="1", device_name="OPTS"), user=admin)
    session.commit()

    test_client.post(
        "/api/v1/devices/OPTS/shots/1/datasets/",
        headers=admin_user_token,
        json={"name": "data1", "level": 1, "url": "s3://opts/1"},
    )

    # Define Mock directly in the router test, ensuring STS assumes work
    mock_provider = mocker.MagicMock()
    mock_provider.generate_credentials.return_value = {
        "opts": S3Credentials(
            access_key_id="r_key",
            secret_access_key="r_sec",
            session_token="r_tok",
            expiration=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
        )
    }
    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=mock_provider,
    )

    # Without query param -> no storage_options (protects list latency)
    resp = test_client.get("/api/v1/devices/OPTS/shots/1/datasets/data1")
    assert resp.status_code == 200
    assert resp.json()[0].get("storage_options") is None

    # With query param -> enriched
    resp2 = test_client.get(
        "/api/v1/devices/OPTS/shots/1/datasets/data1?include_storage_options=true"
    )
    assert resp2.status_code == 200
    data = resp2.json()[0]
    assert data.get("storage_options") is not None
    assert data["storage_options"]["key"] == "r_key"
    assert data["storage_options"]["secret"] == "r_sec"


def test_scientific_metadata_roundtrip(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    sci_meta = [
        {"name": "plasma_current", "value": 0.8, "unit": "MA"},
        {"name": "disrupted", "value": False},
    ]
    response = test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={
            "name": "sci-dataset",
            "level": 1,
            "url": "s3://bucket/sci",
            "scientific_metadata": sci_meta,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["scientific_metadata"] is not None
    assert len(data["scientific_metadata"]) == 2
    assert data["scientific_metadata"][0]["name"] == "plasma_current"
    assert data["scientific_metadata"][1]["value"] is False


def test_create_dataset_without_url(test_client: TestClient, admin_user_token: dict):
    """A Dataset can be registered without a URL; url is null and no distribution is created."""
    response = test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "metadata_only", "level": 1},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "metadata_only"
    assert "url" not in data
    assert "distributions" not in data


def test_create_dataset_without_level(test_client: TestClient, admin_user_token: dict):
    """Processing level is optional; when unset it is omitted from the response."""
    response = test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "no_level", "url": "s3://bucket/no_level"},
    )
    assert response.status_code == 201
    assert "level" not in response.json()


def test_temporal_coverage_roundtrip(
    test_client: TestClient,
    session: Session,
):
    from datetime import timezone

    dataset = DatasetService(session).create(
        DatasetCreate(
            name="ts-data",
            level=0,
            url="s3://bucket/ts",
            access_level=AccessLevel.PUBLIC,
            temporal_start=datetime(2024, 3, 15, 14, 0, tzinfo=timezone.utc),
            temporal_end=datetime(2024, 3, 15, 14, 30, tzinfo=timezone.utc),
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get(f"/api/v1/datasets/id/{dataset.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["temporal_start"].startswith("2024-03-15T14:00:00")
    assert data["temporal_end"].startswith("2024-03-15T14:30:00")

    response = test_client.get(
        f"/api/v1/datasets/id/{dataset.id}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    ld = response.json()
    cov = ld["dct:temporal"]
    assert cov["@type"] == "dct:PeriodOfTime"
    assert cov["startDate"].startswith("2024-03-15T14:00:00")
    assert cov["endDate"].startswith("2024-03-15T14:30:00")
