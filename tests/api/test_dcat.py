from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.device import Device
from app.models.common import AccessLevel


def test_metadata_persistence(session: Session):
    """
    Test that DCAT metadata fields (title, description, publisher) are correctly saved.
    """
    # Create a device with metadata
    device = Device(
        name="test-device-dcat",
        title="Test Device Title",
        description="A test device for DCAT verification",
        publisher="Test Publisher",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(device)
    session.commit()
    session.refresh(device)

    assert device.title == "Test Device Title"
    assert device.description == "A test device for DCAT verification"
    assert device.publisher == "Test Publisher"
    assert device.created_at is not None
    assert device.updated_at is not None


def test_get_catalog(test_client: TestClient, session: Session):
    """
    Test the /api/v1/catalog endpoint returns valid JSON-LD structure.
    """
    # Setup: Create a device to show up in the catalog
    device = Device(
        name="mast",
        title="MAST Upgrade",
        description="Mega Ampere Spherical Tokamak",
        publisher="UKAEA",
        access_level=AccessLevel.PUBLIC,
    )
    session.add(device)
    session.commit()

    response = test_client.get("/api/v1/catalog")
    assert response.status_code == 200
    data = response.json()

    # Check Root Catalog properties
    assert data["@context"] is not None
    assert data["@type"] == "dcat:Catalog"
    assert data["title"] == "Fusion Data Service Catalog"

    # Check Sub-catalogs (Devices)
    sub_catalogs = data.get("dcat:catalog", [])
    assert len(sub_catalogs) > 0

    mast_entry = next(
        (item for item in sub_catalogs if item["identifier"] == "mast"), None
    )
    assert mast_entry is not None
    assert mast_entry["@type"] == "dcat:Catalog"
    assert mast_entry["title"] == "MAST Upgrade"
    assert mast_entry["publisher"] == "UKAEA"
