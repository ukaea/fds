import pytest

from tests.integration.conftest import FDS_URL

pytestmark = pytest.mark.integration


def test_public_dataset_readable_unauthenticated(http_client, seeded_data):
    resp = http_client.get(f"{FDS_URL}/devices/mast/shots/30420/datasets/equilibrium")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_restricted_dataset_hidden_unauthenticated(http_client, seeded_data):
    # Restricted dataset metadata is hidden from unauthenticated requests —
    # FDS returns an empty list (200) rather than 403, so the dataset's existence
    # is not leaked. With a valid token the dataset is visible (see test below).
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/datasets/thomson-raw"
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_restricted_dataset_accessible_with_admin_token(
    http_client, seeded_data, admin_headers
):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/datasets/thomson-raw",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_storage_options_vended_for_public_dataset(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/datasets/equilibrium",
        params={"include_storage_options": "true"},
    )
    assert resp.status_code == 200
    ds = resp.json()[0]
    assert ds.get("storage_options") is not None


def test_storage_options_vended_for_restricted_dataset(
    http_client, seeded_data, admin_headers
):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/datasets/thomson-raw",
        headers=admin_headers,
        params={"include_storage_options": "true"},
    )
    assert resp.status_code == 200
    ds = resp.json()[0]
    assert ds.get("storage_options") is not None


def test_raw_collection_is_restricted(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/collections/raw-diagnostics"
    )
    assert resp.status_code in (401, 403)


def test_analysed_collection_is_public(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/collections/analysed"
    )
    assert resp.status_code == 200
