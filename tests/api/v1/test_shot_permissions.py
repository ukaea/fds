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
        "iss": "https://test-idp.com",
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
        "iss": "https://test-idp.com",
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
        "iss": "https://test-idp.com",
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


def test_create_shot_untrusted_issuer_rejected(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    # Override auth: token has the right scope but from an issuer NOT in TRUSTED_IDPS.
    # _filter_scopes will strip all scopes to [], causing check_shot_operator to raise.
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "operator-user",
        "scp": "shot-operator:MAST",
        "iss": "https://untrusted-idp.example.com",
    }

    response = test_client.post(
        "/api/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-untrusted", "access_level": "public"},
    )

    # Assert: scopes stripped → operator check fails → 403
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.clear()


def test_create_shot_anonymous(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    session.commit()

    # Act: Try to create shot WITHOUT token
    # Note: No headers passed
    response = test_client.post(
        "/api/v1/devices/MAST/shots/",
        json={"id": "shot-anon-fail", "access_level": "public"},
    )

    # Assert: Should be Forbidden (403) - NOT Unauthorized (401)
    assert response.status_code == 403
