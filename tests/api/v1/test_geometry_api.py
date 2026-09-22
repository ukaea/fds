"""API surfacing of resolved reference geometry."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.models.coverage import Coverage, DateRange, ShotRange
from app.services.jsonld import map_dataset_to_dcat

THOMSON = Coverage(shot_ranges=[ShotRange(from_shot="150")])


def test_include_geometry_off_by_default(
    test_client: TestClient, make_version, make_signal, admin_user_token: dict
):
    make_version("thomson_geometry", ["thomson_positions"], THOMSON)
    signal = make_signal(["thomson_positions"])
    resp = test_client.get(f"/v1/datasets/id/{signal.id}", headers=admin_user_token)
    assert resp.status_code == 200
    assert "geometry" not in resp.json()


def test_include_geometry_surfaces_versions(
    test_client: TestClient, make_version, make_signal, admin_user_token: dict
):
    version = make_version("thomson_geometry", ["thomson_positions"], THOMSON)
    signal = make_signal(["thomson_positions"])
    resp = test_client.get(
        f"/v1/datasets/id/{signal.id}?include_geometry=true",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    geometry = resp.json()["geometry"]
    assert len(geometry) == 1
    assert geometry[0]["id"] == version.id
    # storage_options are withheld unless include_storage_options is also set.
    assert "storage_options" not in geometry[0]


def test_include_geometry_with_storage_options(
    test_client: TestClient, make_version, make_signal, admin_user_token: dict
):
    make_version("thomson_geometry", ["thomson_positions"], THOMSON)
    signal = make_signal(["thomson_positions"])
    resp = test_client.get(
        f"/v1/datasets/id/{signal.id}"
        "?include_geometry=true&include_storage_options=true",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    geometry = resp.json()["geometry"]
    assert len(geometry) == 1
    assert geometry[0]["storage_options"] is not None


def test_multi_role_bundle_deduped(
    test_client: TestClient, make_version, make_signal, admin_user_token: dict
):
    roles = ["thomson_positions", "bolometer_chords"]
    bundle = make_version("bundle", roles, Coverage(shots=["150"]))
    signal = make_signal(roles)
    resp = test_client.get(
        f"/v1/datasets/id/{signal.id}?include_geometry=true",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    geometry = resp.json()["geometry"]
    # Two references landing on one bundle collapse to a single entry.
    assert len(geometry) == 1
    assert geometry[0]["id"] == bundle.id


def test_jsonld_qualified_relation_resolved_geometry(
    datasets, make_version, make_signal
):
    coverage = Coverage(
        date_ranges=[
            DateRange(from_date=datetime(2008, 1, 1), to_date=datetime(2009, 1, 1))
        ]
    )
    make_version("thomson_geometry", ["thomson_positions"], coverage)
    signal = make_signal(["thomson_positions"])

    read_model = datasets.to_read_model(signal, include_geometry=True)
    doc = map_dataset_to_dcat(
        read_model, "http://testserver", geometry=read_model.geometry
    )
    relations = doc["dcat:qualifiedRelation"]
    assert len(relations) == 1
    entry = relations[0]
    assert entry["@type"] == "dcat:Relationship"
    assert entry["dcat:hadRole"]["@id"] == "fuel:geometry"
    relation = entry["dct:relation"]
    assert relation["dct:temporal"]["startDate"].startswith("2008-01-01")
    assert relation["dct:temporal"]["endDate"].startswith("2009-01-01")
    assert "dct:references" not in doc
