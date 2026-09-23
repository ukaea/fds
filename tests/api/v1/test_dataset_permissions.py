from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def test_public_dataset_anonymous_access(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    # Setup: Device (Public), Shot (Public), Dataset (Public)
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="100", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="mag_field",
            level=0,
            url="s3://bucket/mag_field.nc",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read anonymously
    response = test_client.get("/v1/devices/MAST/shots/100/datasets/mag_field")

    # Assert: Success
    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "mag_field"
    assert data[0]["effective_access_level"] == "public"


def test_restricted_dataset_anonymous_access_forbidden(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    # Setup: Dataset Restricted
    DeviceService(session).create(
        DeviceCreate(name="JET", type="Tokamak"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(device_name="JET", id="200", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="core_temp",
            level=1,
            url="s3://bucket/core_temp.nc",
            device_name="JET",
            shot_id="200",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    # Act
    response = test_client.get("/v1/devices/JET/shots/200/datasets/core_temp")

    # Assert: 200 with empty list (restricted resources are hidden, not rejected)
    assert response.status_code == 200
    assert response.json() == []


def test_dataset_inheritance_override(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """
    Test: Dataset (Public) inside Shot (Restricted).
    Result: Should be Public (Specific Overrides General).
    """
    # Setup: Device (Restricted), Shot (Restricted)
    DeviceService(session).create(
        DeviceCreate(name="ITER", type="Tokamak"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(device_name="ITER", id="300", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    # Dataset explicitly PUBLIC
    DatasetService(session).create(
        DatasetCreate(
            name="summary_data",
            level=2,
            url="s3://iter/summary.json",
            device_name="ITER",
            shot_id="300",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read anonymously
    response = test_client.get("/v1/devices/ITER/shots/300/datasets/summary_data")

    # Assert: Success (200) because Dataset Level (Public) wins
    assert response.status_code == 200
    assert response.json()[0]["effective_access_level"] == "public"


def test_dataset_inheritance_fallback(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """
    Test: Dataset (None) inside Shot (Restricted).
    Result: Should be Restricted (Inherited).
    """
    # Setup
    DeviceService(session).create(
        DeviceCreate(name="D3D", type="Tokamak"), user=admin_user
    )
    # Shot Restricted
    ShotService(session).create(
        ShotCreate(device_name="D3D", id="400", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    # Dataset defaults (None)
    DatasetService(session).create(
        DatasetCreate(
            name="raw_data",
            level=0,
            url="s3://d3d/raw",
            device_name="D3D",
            shot_id="400",
        ),
        user=admin_user,
    )
    session.commit()

    # Act: Read anonymously
    response = test_client.get("/v1/devices/D3D/shots/400/datasets/raw_data")

    # Assert: 200 with empty list (restricted resources are hidden, not rejected)
    assert response.status_code == 200
    assert response.json() == []


def test_list_filtering(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """
    Test: List endpoint filters out restricted datasets for anonymous user.
    """
    DeviceService(session).create(
        DeviceCreate(name="W7X", type="Stellarator"), user=admin_user
    )
    ShotService(session).create(
        ShotCreate(device_name="W7X", id="500", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )

    # 1. Public Dataset
    DatasetService(session).create(
        DatasetCreate(
            name="visible",
            level=0,
            url="s3://w7x/vis",
            device_name="W7X",
            shot_id="500",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )
    # 2. Restricted Dataset
    DatasetService(session).create(
        DatasetCreate(
            name="hidden",
            level=0,
            url="s3://w7x/hidden",
            device_name="W7X",
            shot_id="500",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    # Act
    response = test_client.get("/v1/devices/W7X/shots/500/datasets/")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "visible"
