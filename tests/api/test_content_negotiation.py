from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.negotiation import prefers_jsonld
from app.main import app
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import Device, DeviceCreate
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from tests.conftest import resource


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
    data = resource(response.json())
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
    document = response.json()
    data = resource(document)
    assert data["creator"] == "Dr. A. Example"
    assert document["@context"]["creator"] == "dct:creator"


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
    data = resource(response.json())
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
    cov = resource(response.json())["dct:temporal"]
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
    data = resource(response.json())
    assert "@type" in data
    assert data["@type"] == "dcat:Dataset"
    assert data["title"] == "Negotiation Test Dataset"


@pytest.mark.parametrize(
    ("accept", "jsonld"),
    [
        (None, False),
        ("*/*", False),
        ("text/html,application/xhtml+xml,*/*;q=0.8", False),
        ("application/*", False),
        ("application/json", False),
        ("application/ld+json", True),
        ('application/ld+json;profile="http://www.w3.org/ns/json-ld#compacted"', True),
        ("application/ld+json, application/json", True),
        ("application/ld+json, */*;q=0.1", True),
        ("application/ld+json, application/json;q=0.9", True),
        ("application/json, application/ld+json;q=0.5", False),
        ("application/ld+json;q=0", False),
        ("application/ld+json;q=0, */*", False),
        ("application/ld+json;q=high", False),
    ],
)
def test_prefers_jsonld(accept: str | None, jsonld: bool):
    assert prefers_jsonld(accept) is jsonld


@pytest.fixture
def negotiated(session: Session, admin_user: AuthenticatedUser) -> dict[str, int]:
    """A public device and shot, a dataset on the shot, and a collection at each
    level, for the routes that answer in JSON or JSON-LD. Returns the dataset's
    and the global collection's ids."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(ShotCreate(id="30421", device_name="MAST"), admin_user)
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="efit",
            device_name="MAST",
            shot_id="30421",
            url="s3://mast/30421/efit",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    collections = CollectionService(session)
    campaign = collections.create(
        CollectionCreate(name="campaign", access_level=AccessLevel.PUBLIC), admin_user
    )
    collections.create(CollectionCreate(name="coils", device_name="MAST"), admin_user)
    collections.create(
        CollectionCreate(name="jintrac", device_name="MAST", shot_id="30421"),
        admin_user,
    )
    session.commit()
    assert dataset.id is not None
    assert campaign.id is not None
    return {"dataset": dataset.id, "collection": campaign.id}


@pytest.mark.parametrize(
    "path",
    [
        "/v1/devices/MAST",
        "/v1/devices/MAST/shots/30421",
        "/v1/datasets/id/{dataset}",
        "/v1/collections/id/{collection}",
        "/v1/collections/campaign",
        "/v1/devices/MAST/collections/coils",
        "/v1/devices/MAST/shots/30421/collections/jintrac",
        "/v1/datasets",
        "/v1/devices/MAST/datasets",
        "/v1/devices/MAST/shots/30421/datasets",
    ],
)
def test_negotiated_routes_answer_as_the_caller_prefers(
    test_client: TestClient, negotiated: dict[str, int], path: str
):
    url = path.format(**negotiated)

    plain = test_client.get(url)
    linked = test_client.get(url, headers={"Accept": "application/ld+json"})
    rather_json = test_client.get(
        url, headers={"Accept": "application/json, application/ld+json;q=0.5"}
    )

    assert plain.headers["content-type"] == "application/json"
    assert linked.headers["content-type"] == "application/ld+json"
    assert rather_json.headers["content-type"] == "application/json"
    assert plain.headers["vary"] == "Accept"
    assert linked.headers["vary"] == "Accept"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/devices/{device_name}",
        "/v1/devices/{device_name}/shots/{shot_id}",
        "/v1/datasets/id/{id}",
        "/v1/collections/id/{id}",
        "/v1/collections/{name}",
        "/v1/devices/{device_name}/collections/{name}",
        "/v1/devices/{device_name}/shots/{shot_id}/collections/{name}",
        "/v1/datasets",
        "/v1/devices/{device_name}/datasets",
        "/v1/devices/{device_name}/shots/{shot_id}/datasets",
    ],
)
def test_openapi_offers_json_ld_on_negotiated_routes(path: str):
    answer = app.openapi()["paths"][path]["get"]["responses"]["200"]

    assert set(answer["content"]) == {"application/json", "application/ld+json"}


@pytest.mark.parametrize("path", ["/datasets/{id}", "/v1/catalog"])
def test_openapi_gives_json_ld_only_routes_as_json_ld(path: str):
    answer = app.openapi()["paths"][path]["get"]["responses"]["200"]

    assert set(answer["content"]) == {"application/ld+json"}
