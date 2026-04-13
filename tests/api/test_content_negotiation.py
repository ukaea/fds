from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.dataset import DatasetCreate
from app.models.device import Device
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.dataset_service import DatasetService


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
    response = test_client.get(f"/api/v1/devices/{device.name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "name" in data
    assert "@type" not in data

    # 2. JSON-LD
    response = test_client.get(
        f"/api/v1/devices/{device.name}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    assert "@type" in data
    assert data["@type"] == "dcat:Catalog"
    assert data["title"] == "Negotiation Test Device"


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
    response = test_client.get(f"/api/v1/datasets/id/{dataset.id}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "name" in data
    assert "@type" not in data

    # 2. JSON-LD — by ID
    response = test_client.get(
        f"/api/v1/datasets/id/{dataset.id}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    assert "@type" in data
    assert data["@type"] == "dcat:Dataset"
    assert data["title"] == "Negotiation Test Dataset"
