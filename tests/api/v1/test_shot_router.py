from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import DeviceCreate
from app.models.shot import ShotCreate, AccessLevel
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from app.auth.security import AuthenticatedUser

# Dummy admin user for test setup
admin_user = AuthenticatedUser(id="test-admin", scopes=["fds-admin"])


def test_create_shot_global_endpoint(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    device_service.create(DeviceCreate(name="MAST", type="Tokamak"), user=admin_user)
    session.commit()

    shot_data = {"id": "shot-12345", "device_name": "MAST", "access_level": "public"}

    response = client.post(
        "/api/v1/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "shot-12345"
    assert data["access_level"] == "public"
    assert "device_id" not in data
    assert "device" not in data


def test_create_shot_nested_endpoint(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    shot_data = {"id": "shot-54321", "access_level": "public"}

    response = client.post(
        f"/api/v1/devices/{mast.name}/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "shot-54321"


def test_create_shot_conflict(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    device_service.create(DeviceCreate(name="JET", type="Tokamak"), user=admin_user)
    session.commit()

    shot_data = {"id": "shot-conflict", "device_name": "JET"}

    response = client.post(
        f"/api/v1/devices/{mast.name}/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 409
    assert "does match" or "conflict" in response.json()["detail"].lower()


def test_create_shot_missing_device(
    client: TestClient,
    # session: Session,
    admin_user_token: dict,
):
    shot_data = {"id": "shot-no-device"}
    response = client.post(
        "/api/v1/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 422


def test_update_shot_nested_device_change(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    jet = device_service.create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(
            id="shot-to-move", device_name="MAST", access_level=AccessLevel.PUBLIC
        ),
        user=admin_user,
    )
    session.commit()

    # Move from MAST to JET via nested endpoint
    update_data = {"device_name": "JET"}
    response = client.put(
        f"/api/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
        json=update_data,
    )
    assert response.status_code == 200

    # Verify it moved
    updated_shot = shot_service.get(shot.id)
    assert updated_shot.device_id == jet.id

    # Verify old nested path returns 404
    response = client.get(
        f"/api/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
    )
    assert response.status_code == 404


def test_update_shot_nested_mismatch_404(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    device_service.create(DeviceCreate(name="MAST", type="Tokamak"), user=admin_user)
    jet = device_service.create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-on-mast", device_name="MAST"), user=admin_user
    )
    session.commit()

    # Try to update via JET endpoint although it belongs to MAST
    response = client.put(
        f"/api/v1/devices/{jet.name}/shots/{shot.id}",
        headers=admin_user_token,
        json={"access_level": "restricted"},
    )
    assert response.status_code == 404


def test_update_shot_global(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    device_service.create(DeviceCreate(name="MAST", type="Tokamak"), user=admin_user)
    jet = device_service.create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-global-update", device_name="MAST"), user=admin_user
    )
    session.commit()

    # Move from MAST to JET via global endpoint
    update_data = {"device_name": "JET", "access_level": "restricted"}
    response = client.put(
        f"/api/v1/shots/{shot.id}",
        headers=admin_user_token,
        json=update_data,
    )
    assert response.status_code == 200

    updated_shot = shot_service.get(shot.id)
    assert updated_shot.device_id == jet.id
    assert updated_shot.access_level == AccessLevel.RESTRICTED


def test_delete_shot(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=["fds-admin"])

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-to-delete", device_name="MAST"), user=admin_user
    )
    session.commit()

    response = client.delete(
        f"/api/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
    )
    assert response.status_code == 204

    # Verify it's deleted
    assert shot_service.get(shot.id) is None


def test_read_shots_include_device(
    client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    shot_service.create(ShotCreate(id="shot-1", device_name="MAST"), user=admin_user)
    session.commit()

    # Default: device should be excluded
    response = client.get(
        f"/api/v1/devices/{mast.name}/shots/", headers=admin_user_token
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" not in data[0]
    assert "device_id" not in data[0]

    # With include_device=True: device should be present
    response = client.get(
        f"/api/v1/devices/{mast.name}/shots/?include_device=true",
        headers=admin_user_token,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" in data[0]
    assert data[0]["device"]["name"] == "MAST"
    assert "device_id" not in data[0]
