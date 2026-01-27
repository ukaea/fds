from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.shot import AccessLevel, ShotCreate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def test_read_public_shot_anonymous(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Public Shot on MAST
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    shot_service = ShotService(session)
    # Note: AccessLevel.PUBLIC is explicit
    shot = shot_service.create(
        ShotCreate(
            id="shot-public", device_name="MAST", access_level=AccessLevel.PUBLIC
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read without token
    response = test_client.get(f"/api/v1/devices/MAST/shots/{shot.id}")

    # Assert: Success
    assert response.status_code == 200
    assert response.json()["id"] == "shot-public"


def test_read_restricted_shot_anonymous(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: Restricted Shot
    DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    shot_service = ShotService(session)
    # Default is Restricted if not specified to be Public
    # (or explicitly set to RESTRICTED)
    shot = shot_service.create(
        ShotCreate(
            id="shot-restricted", device_name="JET", access_level=AccessLevel.RESTRICTED
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read without token
    response = test_client.get(f"/api/v1/devices/JET/shots/{shot.id}")

    # Assert: Forbidden (403)
    # Since Service raises ForbiddenError, and global exception handler maps it to 403
    assert response.status_code == 403


def test_read_restricted_shot_authenticated(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    non_admin_user_token: dict,
):
    # Setup
    DeviceService(session).create(
        DeviceCreate(name="ITER", type="Tokamak"), user=admin_user
    )
    shot_service = ShotService(session)
    shot = shot_service.create(
        ShotCreate(
            id="shot-auth", device_name="ITER", access_level=AccessLevel.RESTRICTED
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read WITH token (any valid user)
    # non_admin_user_token is a fixture providing a valid bearer
    response = test_client.get(
        f"/api/v1/devices/ITER/shots/{shot.id}", headers=non_admin_user_token
    )

    # Assert: Success
    assert response.status_code == 200
    assert response.json()["id"] == "shot-auth"


def test_list_shots_filtering(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
):
    # Setup: 1 Public, 1 Restricted
    DeviceService(session).create(
        DeviceCreate(name="W7X", type="Stellarator"), user=admin_user
    )
    shot_service = ShotService(session)
    shot_service.create(
        ShotCreate(id="s-pub", device_name="W7X", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    shot_service.create(
        ShotCreate(id="s-priv", device_name="W7X", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    session.commit()

    # Act: List anonymously
    response = test_client.get("/api/v1/devices/W7X/shots/")

    # Assert
    assert response.status_code == 200
    data = response.json()
    ids = [s["id"] for s in data]
    assert "s-pub" in ids
    assert "s-priv" not in ids  # Should be filtered out
