from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.auth.security import AuthenticatedUser

# Dummy users for setup
admin_user = AuthenticatedUser(id="admin", scopes=["fds-admin"])
mast_admin = AuthenticatedUser(id="mast", scopes=["mast_admin"])


def test_create_global_dataset(test_client: TestClient, admin_user_token: dict):
    response = test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "global_const", "level": 1, "data_url": "s3://global"},
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
        json={"name": "machine_params", "level": 1, "data_url": "s3://nstx"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "machine_params"
    assert data["device_name"] == "NSTX"


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
        json={"name": "efit", "level": 2, "data_url": "s3://mast/123/efit"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "efit"
    assert data["device_name"] == "MAST"
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
        json={"name": "plasma_current", "level": 1, "data_url": "s3://url"},
    )

    response = test_client.get("/api/v1/devices/MAST/shots/456/datasets/plasma_current")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "plasma_current"


def test_dataset_name_collision_in_context(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Spherical"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(id="789", device_name="MAST"), user=admin_user
    )
    session.commit()

    payload = {"name": "重复", "level": 1, "data_url": "s3://url"}
    test_client.post(
        "/api/v1/devices/MAST/shots/789/datasets/",
        headers=admin_user_token,
        json=payload,
    )

    # Second time should fail
    response = test_client.post(
        "/api/v1/devices/MAST/shots/789/datasets/",
        headers=admin_user_token,
        json=payload,
    )
    assert response.status_code == 409


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
        json={"name": "illegal", "level": 1, "data_url": "url"},
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
        json={"name": "data_a", "level": 1, "data_url": "url_a"},
    )
    test_client.post(
        "/api/v1/devices/DIII-D/datasets/",
        headers=admin_user_token,
        json={"name": "data_b", "level": 1, "data_url": "url_b"},
    )

    response = test_client.get("/api/v1/devices/DIII-D/datasets/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_read_global_dataset_by_name(test_client: TestClient, admin_user_token: dict):
    test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "global_ref", "level": 1, "data_url": "url"},
    )

    response = test_client.get("/api/v1/datasets/global_ref")
    assert response.status_code == 200
    assert response.json()["name"] == "global_ref"


def test_update_dataset(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    from app.models.dataset import Dataset

    # Create global via API
    test_client.post(
        "/api/v1/datasets/",
        headers=admin_user_token,
        json={"name": "to_update", "level": 1, "data_url": "url"},
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
