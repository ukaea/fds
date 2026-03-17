from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.shot import AccessLevel, ShotCreate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

admin_user = AuthenticatedUser(id="test-admin", scopes=("fds-admin",))


def test_create_shot_nested_endpoint(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    shot_data = {"id": "shot-54321", "access_level": "public"}

    response = test_client.post(
        f"/api/v1/devices/{mast.name}/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "shot-54321"


def test_create_shot_conflict(
    test_client: TestClient,
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

    response = test_client.post(
        f"/api/v1/devices/{mast.name}/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 409
    assert "does match" or "conflict" in response.json()["detail"].lower()


def test_update_shot_nested_device_change(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    _jet = device_service.create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(
            id="shot-to-move", device_name="MAST", access_level=AccessLevel.PUBLIC
        ),
        user=admin_user,
    )
    session.commit()

    # Try to move from MAST to JET via nested endpoint - should fail
    update_data = {"device_name": "JET"}
    response = test_client.put(
        f"/api/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
        json=update_data,
    )
    assert response.status_code == 409

    # Verify it did NOT move
    updated_shot = shot_service.get(("MAST", shot.id))
    assert updated_shot.device_name == "MAST"


def test_update_shot_nested_mismatch_404(
    test_client: TestClient,
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
    response = test_client.put(
        f"/api/v1/devices/{jet.name}/shots/{shot.id}",
        headers=admin_user_token,
        json={"access_level": "restricted"},
    )
    assert response.status_code == 404


def test_delete_shot(
    test_client: TestClient,
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

    response = test_client.delete(
        f"/api/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
    )
    assert response.status_code == 204

    # Verify it's deleted
    assert shot_service.get((mast.id, shot.id)) is None


def test_read_shots_include_device(
    test_client: TestClient,
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
    response = test_client.get(
        f"/api/v1/devices/{mast.name}/shots/", headers=admin_user_token
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" not in data[0]
    assert "device_id" not in data[0]

    # With include_device=True: device should be present
    response = test_client.get(
        f"/api/v1/devices/{mast.name}/shots/?include_device=true",
        headers=admin_user_token,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" in data[0]
    assert data[0]["device"]["name"] == "MAST"
    assert "device_id" not in data[0]
