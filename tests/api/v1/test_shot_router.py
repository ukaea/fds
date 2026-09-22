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
        f"/v1/devices/{mast.name}/shots/",
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
        f"/v1/devices/{mast.name}/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 409
    detail = response.json()["detail"].lower()
    assert "does not match" in detail


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
        f"/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
        json=update_data,
    )
    assert response.status_code == 409

    # Verify it did NOT move
    updated_shot = shot_service.get(("MAST", shot.id))
    assert updated_shot is not None
    assert updated_shot.device_name == "mast"


def test_update_shot_nested_mismatch_404(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

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
        f"/v1/devices/{jet.name}/shots/{shot.id}",
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
    admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-to-delete", device_name="MAST"), user=admin_user
    )
    session.commit()

    response = test_client.delete(
        f"/v1/devices/{mast.name}/shots/{shot.id}",
        headers=admin_user_token,
    )
    assert response.status_code == 204

    # Verify it's deleted
    assert shot_service.get((mast.name, shot.id)) is None


def test_delete_shot_unauthorized(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
    jet_admin_user_token: dict,
):
    device_service = DeviceService(session)
    shot_service = ShotService(session)
    admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))

    mast = device_service.create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-protected", device_name="MAST"), user=admin_user
    )
    session.commit()

    response = test_client.delete(
        f"/v1/devices/{mast.name}/shots/{shot.id}",
        headers=jet_admin_user_token,
    )
    assert response.status_code == 403

    assert shot_service.get((mast.name, shot.id)) is not None


def test_scientific_metadata_roundtrip(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    sci_meta = [
        {"name": "plasma_current", "value": 0.8, "unit": "MA"},
        {"name": "confinement_mode", "value": "H-mode"},
        {"name": "disrupted", "value": False},
    ]
    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers=admin_user_token,
        json={
            "id": "sci-30420",
            "access_level": "public",
            "scientific_metadata": sci_meta,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["scientific_metadata"] is not None
    assert len(data["scientific_metadata"]) == 3
    assert data["scientific_metadata"][0]["name"] == "plasma_current"
    assert data["scientific_metadata"][0]["unit"] == "MA"
    assert data["scientific_metadata"][2]["value"] is False


def test_shot_metadata_fields_roundtrip(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict,
):
    device_service = DeviceService(session)
    device_service.create(DeviceCreate(name="MAST", type="Tokamak"), user=admin_user)
    session.commit()

    shot_at = "2024-03-15T14:32:00+00:00"
    shot_data = {
        "id": "30420",
        "shot_at": shot_at,
        "publisher": "UKAEA",
        "creator": "J. Smith",
        "access_level": "public",
    }

    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers=admin_user_token,
        json=shot_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["shot_at"].startswith("2024-03-15T14:32:00")
    assert data["publisher"] == "UKAEA"
    assert data["creator"] == "J. Smith"

    response = test_client.get("/v1/devices/MAST/shots/30420", headers=admin_user_token)
    assert response.status_code == 200
    data = response.json()
    assert data["shot_at"].startswith("2024-03-15T14:32:00")
    assert data["creator"] == "J. Smith"


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
        f"/v1/devices/{mast.name}/shots/", headers=admin_user_token
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" not in data[0]
    assert "device_id" not in data[0]

    # With include_device=True: device should be present
    response = test_client.get(
        f"/v1/devices/{mast.name}/shots/?include_device=true",
        headers=admin_user_token,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "device" in data[0]
    assert data[0]["device"]["name"] == "mast"
    assert "device_id" not in data[0]
