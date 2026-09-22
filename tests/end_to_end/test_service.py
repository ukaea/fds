"""The service is up, serves its API, and round-trips a resource."""

import httpx
import pytest

from tests.end_to_end.conftest import FDS_URL

pytestmark = pytest.mark.end_to_end

ROOT = FDS_URL.removesuffix("/v1")


def test_health_is_served(http_client: httpx.Client):
    response = http_client.get(f"{ROOT}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_describes_the_api(http_client: httpx.Client):
    response = http_client.get(f"{ROOT}/openapi.json")
    assert response.status_code == 200
    assert "/v1/devices/" in response.json()["paths"]


def test_public_metadata_is_readable_without_a_token(http_client: httpx.Client, device):
    created = device(access_level="public")

    response = http_client.get(f"{FDS_URL}/devices/{created['name']}")
    assert response.status_code == 200
    assert response.json()["name"] == created["name"]


def test_create_read_delete_round_trip(
    http_client: httpx.Client, admin_headers: dict[str, str], device
):
    """Writes reach the database and are visible on a later request."""
    created = device()
    name = created["name"]

    listed = http_client.get(f"{FDS_URL}/devices/", headers=admin_headers)
    assert listed.status_code == 200
    assert name in {d["name"] for d in listed.json()}

    removed = http_client.delete(f"{FDS_URL}/devices/{name}", headers=admin_headers)
    assert removed.status_code == 204
    assert http_client.get(f"{FDS_URL}/devices/{name}").status_code == 404


def test_json_ld_is_served_when_negotiated(
    http_client: httpx.Client, admin_headers: dict[str, str], device
):
    created = device(access_level="public")

    response = http_client.get(
        f"{FDS_URL}/devices/{created['name']}",
        headers={"Accept": "application/ld+json"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")

    body = response.json()
    assert "@context" in body
    # Identifiers are built from the host the request arrived on, so they name
    # whatever address this deployment is reached at.
    assert body["@id"].endswith(f"/v1/devices/{created['name']}")
