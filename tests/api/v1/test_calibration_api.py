"""API surfacing of resolved reference calibration (ADR-0037)."""

from fastapi.testclient import TestClient

from app.models.reference import ReferenceCoverage
from app.services.jsonld import map_dataset_to_dcat

COVERS_150 = ReferenceCoverage(shots=["150"])


def test_include_calibration_off_by_default(
    test_client: TestClient, make_cal_version, make_cal_signal, admin_user_token: dict
):
    make_cal_version("gain", ["gain"], COVERS_150, stage=1)
    signal = make_cal_signal(["gain"])
    resp = test_client.get(f"/api/v1/datasets/id/{signal.id}", headers=admin_user_token)
    assert resp.status_code == 200
    assert "calibration" not in resp.json()


def test_include_calibration_surfaces_chain_in_stage_order(
    test_client: TestClient, make_cal_version, make_cal_signal, admin_user_token: dict
):
    absolute = make_cal_version("absolute", ["signal"], COVERS_150, stage=3)
    gain = make_cal_version("gain", ["signal"], COVERS_150, stage=1)
    wavelength = make_cal_version("wavelength", ["signal"], COVERS_150, stage=2)
    signal = make_cal_signal(["signal"])
    resp = test_client.get(
        f"/api/v1/datasets/id/{signal.id}?include_calibration=true",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    chain = resp.json()["calibration"]
    assert [entry["id"] for entry in chain] == [gain.id, wavelength.id, absolute.id]
    # storage_options are withheld unless include_storage_options is also set.
    assert "storage_options" not in chain[0]


def test_include_calibration_with_storage_options(
    test_client: TestClient, make_cal_version, make_cal_signal, admin_user_token: dict
):
    make_cal_version("gain", ["signal"], COVERS_150, stage=1)
    signal = make_cal_signal(["signal"])
    resp = test_client.get(
        f"/api/v1/datasets/id/{signal.id}"
        "?include_calibration=true&include_storage_options=true",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    chain = resp.json()["calibration"]
    assert chain[0]["storage_options"] is not None


def test_jsonld_calibration_qualified_relation_ordered(
    datasets, make_cal_version, make_cal_signal
):
    absolute = make_cal_version("absolute", ["signal"], COVERS_150, stage=2)
    gain = make_cal_version("gain", ["signal"], COVERS_150, stage=1)
    signal = make_cal_signal(["signal"])

    read_model = datasets.to_read_model(signal, include_calibration=True)
    doc = map_dataset_to_dcat(
        read_model, "http://testserver", calibration=read_model.calibration
    )
    relations = doc["dcat:qualifiedRelation"]
    # A qualified relation per stage, in order, each tagged with the fuel role.
    assert [r["dct:relation"]["@id"].rsplit("/", 1)[-1] for r in relations] == [
        str(gain.id),
        str(absolute.id),
    ]
    assert all(r["dcat:hadRole"]["@id"] == "fuel:calibration" for r in relations)
    # Not conflated with geometry's dct:references.
    assert "dct:references" not in doc
