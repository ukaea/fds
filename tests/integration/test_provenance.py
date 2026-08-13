import pytest

from app.services.jsonld import FUEL_EXECUTOR_ROLE, FUEL_ORCHESTRATOR_ROLE
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
    jintrac_outputs = [ds for ds in resp.json() if ds.get("activity_id") == activity_id]
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


def test_efit_dataset_jsonld_records_delegation(http_client):
    """The EFIT run's JSON-LD shows the executor acted on behalf of the scheduler.

    The scheduler orchestrates the between-shot EFIT analyses, not the JINTRAC
    simulation, so the delegation hangs off an EFIT-produced equilibrium.
    """
    dataset = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30421/datasets/equilibrium"
    ).json()[0]

    resp = http_client.get(
        f"{FDS_URL}/datasets/id/{dataset['id']}",
        headers={"Accept": "application/ld+json"},
    )
    assert resp.status_code == 200
    prov = resp.json()["prov:wasGeneratedBy"]

    # The executor (EFIT) carries prov:actedOnBehalfOf to the orchestrating scheduler.
    assert "prov:actedOnBehalfOf" in prov["prov:wasAssociatedWith"]
    roles = {a["prov:hadRole"]["@id"] for a in prov["prov:qualifiedAssociation"]}
    assert {FUEL_EXECUTOR_ROLE, FUEL_ORCHESTRATOR_ROLE} <= roles


def test_jintrac_run_is_discoverable_by_its_bundle(http_client):
    """A run is findable as a run because its Collection carries the claim.

    The Activity holds no scientific metadata by design, so this query has to be
    answered by the bundle or not at all.
    """
    resp = http_client.get(
        f"{FDS_URL}/devices/mast/shots/30420/collections",
        params={"annotation": "confinement_mode:H-mode"},
    )

    assert resp.status_code == 200
    collections = resp.json()
    assert [c["name"] for c in collections] == ["jintrac-v220922"]
    assert collections[0]["activity_id"] is not None
