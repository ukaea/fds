import pytest

from tests.integration.conftest import FDS_URL

pytestmark = pytest.mark.integration

LD_HEADERS = {"Accept": "application/ld+json"}


def test_dataset_jsonld_response(http_client, seeded_data):
    eq_id = seeded_data["mast_30421_equilibrium_id"]
    resp = http_client.get(f"{FDS_URL}/datasets/id/{eq_id}", headers=LD_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "@context" in body
    assert "dcat:distribution" in body


def test_dataset_jsonld_has_access_url(http_client, seeded_data):
    eq_id = seeded_data["mast_30421_equilibrium_id"]
    resp = http_client.get(f"{FDS_URL}/datasets/id/{eq_id}", headers=LD_HEADERS)
    assert resp.status_code == 200
    distributions = resp.json().get("dcat:distribution", [])
    assert len(distributions) > 0
    urls = [d.get("dcat:accessURL") or d.get("dcat:downloadURL") for d in distributions]
    assert any(urls)


def test_dataset_with_activity_has_provenance(http_client, seeded_data):
    eq_id = seeded_data["mast_30421_equilibrium_id"]
    resp = http_client.get(f"{FDS_URL}/datasets/id/{eq_id}", headers=LD_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert "prov:wasGeneratedBy" in body


def test_collection_jsonld_is_catalog(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/collections/jintrac-v220922",
        headers=LD_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("@type") == "dcat:Catalog"
