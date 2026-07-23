import pytest

from tests.integration.conftest import FDS_URL

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("seeded_data")]


def test_jintrac_activity_has_inputs(http_client, seeded_data):
    activity_id = seeded_data["jintrac_activity_id"]
    resp = http_client.get(f"{FDS_URL}/activities/{activity_id}/inputs")
    assert resp.status_code == 200
    input_names = {ds["name"] for ds in resp.json()}
    assert {"equilibrium", "magnetics", "thomson_scattering"}.issubset(input_names)


def test_equilibrium_dataset_has_activity(http_client):
    resp = http_client.get(f"{FDS_URL}/devices/mast/shots/30421/datasets/equilibrium")
    assert resp.status_code == 200
    ds = resp.json()[0]
    assert ds["activity_id"] is not None


def test_jintrac_outputs_share_activity_id(http_client, seeded_data):
    activity_id = seeded_data["jintrac_activity_id"]
    resp = http_client.get(f"{FDS_URL}/devices/mast/shots/30420/datasets")
    assert resp.status_code == 200
    jintrac_outputs = [
        ds
        for ds in resp.json()
        if ds.get("level") == 3 and ds.get("activity_id") == activity_id
    ]
    output_names = {ds["name"] for ds in jintrac_outputs}
    assert {"equilibrium", "core_profiles", "core_sources"}.issubset(output_names)


def test_jintrac_collection_activity_matches_outputs(http_client):
    col_resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/collections/jintrac-v220922"
    )
    assert col_resp.status_code == 200
    col = col_resp.json()
    collection_activity_id = col["activity_id"]

    datasets = col.get("datasets") or []
    assert len(datasets) > 0
    for ds in datasets:
        assert ds["activity_id"] == collection_activity_id
