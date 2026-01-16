from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.common import AccessLevel
from app.models.dataset import Dataset
from app.models.device import Device


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
    Test that the dataset endpoint (global) respects the Accept header.
    """
    # Setup
    dataset = Dataset(
        name="test-dataset-negotiation",
        title="Negotiation Test Dataset",
        description="A dataset for testing content negotiation",
        publisher="Test Publisher",
        access_level=AccessLevel.PUBLIC,
        level=0,
        data_url="s3://test-bucket/data",
    )
    session.add(dataset)
    session.commit()

    # 1. Default (JSON)
    response = test_client.get(f"/api/v1/datasets/{dataset.name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    data = response.json()
    assert "name" in data
    assert "@type" not in data

    # 2. JSON-LD
    response = test_client.get(
        f"/api/v1/datasets/{dataset.name}", headers={"Accept": "application/ld+json"}
    )
    assert response.status_code == 200
    assert "application/ld+json" in response.headers["content-type"]
    data = response.json()
    assert "@type" in data
    assert data["@type"] == "dcat:Dataset"
    assert data["title"] == "Negotiation Test Dataset"
