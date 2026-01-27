from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser, get_token_claims
from app.main import app
from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


def test_create_shot_as_operator_success(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    # Override auth to be a shot operator for MAST
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "operator-user",
        "scp": "shot-operator:MAST",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/api/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-op-1", "access_level": "public"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["id"] == "shot-op-1"

    # cleanup
    app.dependency_overrides.clear()


def test_create_shot_as_operator_wrong_device(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    # Override auth to be a shot operator for JET (not MAST)
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "operator-user",
        "scp": "shot-operator:JET",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/api/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-op-fail", "access_level": "public"},
    )

    # Assert: Should be Forbidden
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.clear()


def test_create_shot_no_scopes(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    # Override auth to be a regular authenticated user with no special scopes
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "regular-user",
        "scp": "openid profile email",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/api/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-fail", "access_level": "public"},
    )

    # Assert
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.clear()
