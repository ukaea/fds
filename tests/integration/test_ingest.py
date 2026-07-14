import pytest

from tests.integration.conftest import FDS_URL

pytestmark = pytest.mark.integration


def test_devices_registered(http_client, seeded_data):
    for device in ("mast", "mast-upgrade"):
        resp = http_client.get(f"{FDS_URL}/devices/{device}")
        assert resp.status_code == 200, f"Device {device!r} not found"


def test_shots_registered(http_client, seeded_data):
    for device, shot_id in [
        ("mast", "30420"),
        ("mast", "30421"),
        ("mast-upgrade", "50000"),
    ]:
        resp = http_client.get(f"{FDS_URL}/devices/{device}/shots/{shot_id}")
        assert resp.status_code == 200, f"Shot {device}/{shot_id} not found"


def test_mast_datasets_registered(http_client, seeded_data):
    for shot_id in ("30420", "30421"):
        resp = http_client.get(f"{FDS_URL}/devices/mast/shots/{shot_id}/datasets")
        assert resp.status_code == 200
        names = {ds["name"] for ds in resp.json()}
        assert "equilibrium" in names
        assert "magnetics" in names
        assert "thomson_scattering" in names


def test_sources_registered(http_client, seeded_data):
    for source in ("efit", "jintrac", "intershot-scheduler"):
        resp = http_client.get(f"{FDS_URL}/sources/{source}")
        assert resp.status_code == 200, f"Source {source!r} not found"


def test_experiment_data_collections_registered(http_client, seeded_data):
    for shot_id in ("30420", "30421"):
        resp = http_client.get(
            f"{FDS_URL}/devices/mast/shots/{shot_id}/collections/experiment-data"
        )
        assert resp.status_code == 200
        col = resp.json()
        assert col["activity_id"] is not None


def test_jintrac_collection_registered(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/collections/jintrac-v220922"
    )
    assert resp.status_code == 200
    col = resp.json()
    assert col["activity_id"] == seeded_data["jintrac_activity_id"]
    assert col["id"] == seeded_data["jintrac_collection_id"]


def test_mast_upgrade_raw_collection_registered(
    http_client, seeded_data, admin_headers
):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/collections/raw-diagnostics",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == seeded_data["mast_upgrade_raw_collection_id"]


def test_mast_upgrade_analysed_collection_registered(http_client, seeded_data):
    resp = http_client.get(
        f"{FDS_URL}/devices/mast-upgrade/shots/50000/collections/analysed"
    )
    assert resp.status_code == 200
    col = resp.json()
    assert col["id"] == seeded_data["mast_upgrade_analysed_collection_id"]
    assert col["root_url"] is not None


def test_seed_all_is_idempotent(admin_headers):
    from demo.seed_metadata import seed_all

    result1 = seed_all(FDS_URL, admin_headers)
    result2 = seed_all(FDS_URL, admin_headers)
    assert result1 == result2
