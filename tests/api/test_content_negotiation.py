from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.dataset import DatasetCreate
from app.models.device import Device, DeviceCreate
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def test_content_negotiation_device(test_client: TestClient, session: Session):
    """
    Test that the device endpoint respects the Accept header.
    """
    # Setup
    device = Device(
        name="test-device-negotiation",
        title="Negotiation Test Device",
        description="A device for testing content negotiation",
        publisher="Test Publisher",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(device)
    session.commit()

    # 1. Default (JSON)
    response = test_client.get(f"/v1/devices/{device.name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "name" in data
    assert "@type" not in data

    # 2. JSON-LD
    response = test_client.get(
        f"/v1/devices/{device.name}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    assert "@type" in data
    assert data["@type"] == "dcat:Catalog"
    assert data["title"] == "Negotiation Test Device"


def test_creator_in_device_jsonld(test_client: TestClient, session: Session):
    device = Device(
        name="test-device-creator",
        title="Creator Test Device",
        publisher="UKAEA",
        creator="Dr. A. Example",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(device)
    session.commit()

    response = test_client.get(
        f"/v1/devices/{device.name}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["creator"] == "Dr. A. Example"
    assert data["@context"]["creator"] == "dct:creator"


def test_content_negotiation_shot(test_client: TestClient, session: Session):
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), user=admin)
    shot = ShotService(session).create(
        ShotCreate(
            id="30420",
            device_name="MAST",
            shot_at=datetime(2024, 3, 15, 14, 32, tzinfo=UTC),
            shot_end=datetime(2024, 3, 15, 14, 37, tzinfo=UTC),
            creator="J. Smith",
            publisher="UKAEA",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin,
    )
    session.commit()

    response = test_client.get(
        f"/v1/devices/MAST/shots/{shot.id}",
        headers={"Accept": "application/ld+json"},
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    # A Shot is a grouping with no store of its own, so it is a catalog.
    assert data["@type"] == "dcat:Catalog"
    assert data["identifier"] == "30420"
    assert data["creator"] == "J. Smith"
    assert data["publisher"] == "UKAEA"
    # Closed period: both ends known.
    cov = data["dct:temporal"]
    assert cov["@type"] == "dct:PeriodOfTime"
    assert cov["startDate"].startswith("2024-03-15T14:32:00")
    assert cov["endDate"].startswith("2024-03-15T14:37:00")


def test_content_negotiation_shot_open_period(
    test_client: TestClient, session: Session
):
    """A shot with only a start time maps to an open PeriodOfTime (no endDate)."""
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), user=admin)
    ShotService(session).create(
        ShotCreate(
            id="30421",
            device_name="MAST",
            shot_at=datetime(2024, 3, 15, 14, 32, tzinfo=UTC),
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin,
    )
    session.commit()

    response = test_client.get(
        "/v1/devices/MAST/shots/30421",
        headers={"Accept": "application/ld+json"},
    )
    assert response.status_code == 200
    cov = response.json()["dct:temporal"]
    assert cov["@type"] == "dct:PeriodOfTime"
    assert cov["startDate"].startswith("2024-03-15T14:32:00")
    assert "endDate" not in cov


def test_content_negotiation_dataset(test_client: TestClient, session: Session):
    """
    Test that the dataset endpoint (by ID) respects the Accept header.
    """
    # Setup
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="test-dataset-negotiation",
            title="Negotiation Test Dataset",
            description="A dataset for testing content negotiation",
            publisher="Test Publisher",
            access_level=AccessLevel.PUBLIC,
            level=0,
            url="s3://test-bucket/data",
        ),
        user=admin,
    )

    # 1. Default (JSON) — by ID
    response = test_client.get(f"/v1/datasets/id/{dataset.id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "name" in data
    assert "@type" not in data

    # 2. JSON-LD — by ID
    response = test_client.get(
        f"/v1/datasets/id/{dataset.id}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    assert "@type" in data
    assert data["@type"] == "dcat:Dataset"
    assert data["title"] == "Negotiation Test Dataset"
