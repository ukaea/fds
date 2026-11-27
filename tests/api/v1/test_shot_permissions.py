from fastapi.testclient import TestClient
from sqlmodel import Session

from fds.auth.security import AuthenticatedUser, get_token_claims
from fds.main import app
from fds.models.device import DeviceCreate
from fds.services.device_service import DeviceService


def test_create_shot_as_device_writer(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    # Override auth to hold the role MAST lists as a write role
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "device-writer",
        "scp": "mast-write",
        "iss": "https://test-idp.com",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-op-1", "access_level": "public"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json()["id"] == "shot-op-1"

    # cleanup
    app.dependency_overrides.pop(get_token_claims, None)


def test_create_shot_as_another_devices_writer(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    # Override auth to hold JET's write role, not MAST's
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "device-writer",
        "scp": "jet-write",
        "iss": "https://test-idp.com",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-op-fail", "access_level": "public"},
    )

    # Assert: Should be Forbidden
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.pop(get_token_claims, None)


def test_create_shot_as_device_reader_refused(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "reader",
        "scp": "mast-read",
        "iss": "https://test-idp.com",
    }

    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-read-fail", "access_level": "public"},
    )

    assert response.status_code == 403
    assert "mast-write" in response.json()["detail"]

    app.dependency_overrides.pop(get_token_claims, None)


def test_create_shot_no_roles(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    # Override auth to be a regular authenticated user with no roles
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "regular-user",
        "scp": "openid profile email",
        "iss": "https://test-idp.com",
    }

    # Act: Try to create shot for MAST
    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-fail", "access_level": "public"},
    )

    # Assert
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.pop(get_token_claims, None)


def test_create_shot_untrusted_issuer_rejected(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    # Override auth: token has the right role but from an issuer NOT in TRUSTED_IDPS.
    # _filter_roles will strip all roles to [], so the write check refuses.
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "device-writer",
        "scp": "mast-write",
        "iss": "https://untrusted-idp.example.com",
    }

    response = test_client.post(
        "/v1/devices/MAST/shots/",
        headers={"Authorization": "Bearer fake"},
        json={"id": "shot-untrusted", "access_level": "public"},
    )

    # Assert: roles stripped → write check fails → 403
    assert response.status_code == 403

    # cleanup
    app.dependency_overrides.pop(get_token_claims, None)


def test_create_shot_anonymous(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Create Device
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            type="Tokamak",
            write_roles=["mast-write"],
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Try to create shot WITHOUT token
    # Note: No headers passed
    response = test_client.post(
        "/v1/devices/MAST/shots/",
        json={"id": "shot-anon-fail", "access_level": "public"},
    )

    # Assert: Unauthorized (401), since a token would help
    assert response.status_code == 401
