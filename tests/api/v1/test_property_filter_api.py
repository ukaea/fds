import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.scientific_metadata import ScientificProperty
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

MAST = "MAST"
MAST_U = "MAST-U"

# Every test here reads from the seeded catalogue, so request it once for the
# module rather than as an unused argument on each test.
pytestmark = pytest.mark.usefixtures("annotated_api_catalogue")


@pytest.fixture(name="annotated_api_catalogue")
def annotated_api_catalogue_fixture(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    devices = DeviceService(session)
    shots = ShotService(session)
    datasets = DatasetService(session)

    for device in (MAST, MAST_U):
        devices.create(
            DeviceCreate(name=device, type="Tokamak", access_level=AccessLevel.PUBLIC),
            admin_user,
        )

    for device, shot_id, metadata in [
        (MAST, "30420", None),
        (
            MAST,
            "30421",
            [
                ScientificProperty(name="confinement_mode", value="H-mode"),
                ScientificProperty(name="disruption", value=True),
                ScientificProperty(name="elm", value="type-I"),
            ],
        ),
        (MAST_U, "50000", [ScientificProperty(name="elm", value="type-I")]),
        (MAST_U, "50001", None),
    ]:
        shots.create(
            ShotCreate(
                id=shot_id,
                device_name=device,
                access_level=AccessLevel.PUBLIC,
                scientific_metadata=metadata,
            ),
            admin_user,
        )

    for shot_id in ("50000", "50001"):
        for name in ("equilibrium", "magnetics"):
            datasets.create(
                DatasetCreate(
                    name=name,
                    level=2,
                    device_name=MAST_U,
                    shot_id=shot_id,
                    access_level=AccessLevel.PUBLIC,
                    url=f"s3://data/{shot_id}/{name}.nc",
                ),
                admin_user,
            )
    session.commit()


def test_shots_filtered_by_annotation(test_client: TestClient):
    """Use case: MAST shots that disrupted."""
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots", params={"property": "disruption"}
    )

    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_shots_unfiltered_returns_everything(test_client: TestClient):
    resp = test_client.get(f"/v1/devices/{MAST}/shots")

    assert resp.status_code == 200
    assert sorted(s["id"] for s in resp.json()) == ["30420", "30421"]


def test_repeated_annotation_param_parses_as_a_list(test_client: TestClient):
    """`?annotation=a&annotation=b` must arrive as two annotations, ANDed."""
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots", params={"property": ["disruption", "elm"]}
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]

    resp = test_client.get(
        f"/v1/devices/{MAST}/shots",
        params={"property": ["disruption", "sawtooth"]},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_equality_annotation_filter(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots",
        params={"property": "confinement_mode:H-mode"},
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_malformed_annotation_returns_422(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots", params={"property": "disruption:"}
    )
    assert resp.status_code == 422


def test_datasets_filtered_by_shot_property(test_client: TestClient):
    """Use case: equilibrium datasets from ELMy MAST-U shots, in one request."""
    resp = test_client.get(
        f"/v1/devices/{MAST_U}/datasets",
        params={"name": "equilibrium", "shot_property": "elm"},
    )

    assert resp.status_code == 200
    assert [(d["name"], d["shot_id"]) for d in resp.json()] == [
        ("equilibrium", "50000")
    ]


def test_datasets_name_filter_without_annotations(test_client: TestClient):
    """Without shot_property, both shots' equilibrium datasets come back."""
    resp = test_client.get(
        f"/v1/devices/{MAST_U}/datasets", params={"name": "equilibrium"}
    )

    assert resp.status_code == 200
    assert sorted(d["shot_id"] for d in resp.json()) == ["50000", "50001"]


@pytest.fixture(name="annotated_collections")
def annotated_collections_fixture(
    session: Session, admin_user: AuthenticatedUser, annotated_api_catalogue: None
) -> None:
    """Two run bundles on MAST-U 50000: one simulated H-mode, one did not."""
    collections = CollectionService(session)
    for name, metadata in [
        (
            "jintrac-run-1",
            [ScientificProperty(name="confinement_mode", value="H-mode")],
        ),
        (
            "jintrac-run-2",
            [ScientificProperty(name="confinement_mode", value="L-mode")],
        ),
        ("unannotated-run", None),
    ]:
        collections.create(
            CollectionCreate(
                name=name,
                device_name=MAST_U,
                shot_id="50000",
                access_level=AccessLevel.PUBLIC,
                scientific_metadata=metadata,
            ),
            admin_user,
        )
    session.commit()


@pytest.mark.usefixtures("annotated_collections")
def test_collections_filtered_by_annotation(test_client: TestClient):
    """A run is discoverable because its bundle carries the claim, not the run."""
    resp = test_client.get(
        f"/v1/devices/{MAST_U}/shots/50000/collections",
        params={"property": "confinement_mode:H-mode"},
    )

    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()] == ["jintrac-run-1"]


@pytest.mark.usefixtures("annotated_collections")
def test_collections_filtered_by_annotation_presence(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST_U}/shots/50000/collections",
        params={"property": "confinement_mode"},
    )

    assert resp.status_code == 200
    names = sorted(c["name"] for c in resp.json())
    assert names == ["jintrac-run-1", "jintrac-run-2"]


@pytest.mark.usefixtures("annotated_collections")
def test_unannotated_collection_is_returned_when_unfiltered(test_client: TestClient):
    """A run nobody annotated is still listed; it is only absent from filtered results."""
    resp = test_client.get(f"/v1/devices/{MAST_U}/shots/50000/collections")

    assert resp.status_code == 200
    assert "unannotated-run" in {c["name"] for c in resp.json()}


@pytest.mark.usefixtures("annotated_collections")
def test_collection_scientific_metadata_round_trips(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST_U}/shots/50000/collections/jintrac-run-1"
    )

    assert resp.status_code == 200
    assert resp.json()["scientific_metadata"] == [
        {"name": "confinement_mode", "value": "H-mode"}
    ]


# --- Available properties --------------------------------------------------------


def _prop(body: dict, name: str) -> dict:
    """The one prop entry with this name. Absence is a test failure."""
    match = next((f for f in body["properties"] if f["name"] == name), None)
    assert match is not None, f"no prop named {name!r}"
    return match


def test_shot_available_properties(test_client: TestClient):
    resp = test_client.get(f"/v1/devices/{MAST}/shots/properties")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert _prop(body, "confinement_mode")["values"] == ["H-mode"]
    # A stored JSON true reads as the text the equality filter matches on, so
    # the chip a caller clicks is the value they can filter by.
    assert _prop(body, "disruption")["values"] == ["true"]


def test_properties_omit_fields_that_have_no_value(test_client: TestClient):
    """response_model_exclude_none, so absent means absent rather than null."""
    body = test_client.get(f"/v1/devices/{MAST}/shots/properties").json()
    entry = _prop(body, "elm")

    assert "unit" not in entry
    assert "values" in entry
    assert set(entry) == {"name", "records", "distinct", "kind", "values"}


def test_properties_accept_the_same_parameter_as_the_listing(
    test_client: TestClient,
):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots/properties", params={"property": "disruption"}
    )

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_property_values_can_be_capped(test_client: TestClient):
    body = test_client.get(
        f"/v1/devices/{MAST}/shots/properties", params={"max_values": 0}
    ).json()

    assert all("values" not in f for f in body["properties"])
    assert _prop(body, "elm")["distinct"] == 1


def test_properties_reject_an_out_of_range_cap(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots/properties", params={"max_values": 999}
    )

    assert resp.status_code == 422
    assert "max_values" in resp.json()["detail"]


def test_properties_for_an_unknown_device_are_a_404(test_client: TestClient):
    resp = test_client.get("/v1/devices/NOT-A-DEVICE/shots/properties")

    assert resp.status_code == 404


def test_annotations_segment_does_not_bind_as_a_shot_id(test_client: TestClient):
    """Route order: /shots/properties must not resolve to /shots/{shot_id}.

    Both templates have one segment after /shots/, so declaring them the other
    way round would answer this with a 404 for a shot called "annotations"
    rather than with properties, and nothing else would notice.
    """
    properties = test_client.get(f"/v1/devices/{MAST}/shots/properties")
    assert properties.status_code == 200
    assert "properties" in properties.json()

    shot = test_client.get(f"/v1/devices/{MAST}/shots/30421")
    assert shot.status_code == 200
    assert shot.json()["id"] == "30421"


def test_two_values_of_one_name_widen_the_listing(test_client: TestClient):
    """Selecting two values of one property means either, not neither."""
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots",
        params={"property": ["confinement_mode:H-mode", "elm:type-I"]},
    )

    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_properties_report_a_kind_for_every_name(test_client: TestClient):
    body = test_client.get(f"/v1/devices/{MAST}/shots/properties").json()

    assert {f["name"]: f["kind"] for f in body["properties"]} == {
        "confinement_mode": "term",
        "disruption": "term",
        "elm": "term",
    }


def test_range_bounds_filter_the_listing(test_client: TestClient):
    """Non-numeric values under other names must not break the cast."""
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots", params={"property_min": "disruption:0"}
    )

    assert resp.status_code == 200


def test_a_malformed_range_bound_returns_422(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots/properties",
        params={"property_min": "plasma_current_max:not-a-number"},
    )

    assert resp.status_code == 422
    assert "not a number" in resp.json()["detail"]


def test_annotation_values_sub_resource(test_client: TestClient):
    resp = test_client.get(
        f"/v1/devices/{MAST}/shots/properties/confinement_mode/values"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "confinement_mode"
    assert body["values"] == [{"value": "H-mode", "records": 1}]


def test_values_path_does_not_bind_as_a_shot_id(test_client: TestClient):
    """Route order again: /shots/properties/{name}/values must not be a shot."""
    assert (
        test_client.get(f"/v1/devices/{MAST}/shots/properties/elm/values").status_code
        == 200
    )
    assert test_client.get(f"/v1/devices/{MAST}/shots/30421").status_code == 200
