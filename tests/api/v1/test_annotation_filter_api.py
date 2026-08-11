import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.scientific_metadata import ScientificProperty
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

MAST = "MAST"
MAST_U = "MAST-U"


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


def test_shots_filtered_by_annotation(
    test_client: TestClient, annotated_api_catalogue: None
):
    """Use case: MAST shots that disrupted."""
    resp = test_client.get(
        f"/api/v1/devices/{MAST}/shots", params={"annotation": "disruption"}
    )

    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_shots_unfiltered_returns_everything(
    test_client: TestClient, annotated_api_catalogue: None
):
    resp = test_client.get(f"/api/v1/devices/{MAST}/shots")

    assert resp.status_code == 200
    assert sorted(s["id"] for s in resp.json()) == ["30420", "30421"]


def test_repeated_annotation_param_parses_as_a_list(
    test_client: TestClient, annotated_api_catalogue: None
):
    """`?annotation=a&annotation=b` must arrive as two annotations, ANDed."""
    resp = test_client.get(
        f"/api/v1/devices/{MAST}/shots", params={"annotation": ["disruption", "elm"]}
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]

    resp = test_client.get(
        f"/api/v1/devices/{MAST}/shots",
        params={"annotation": ["disruption", "sawtooth"]},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_equality_annotation_filter(
    test_client: TestClient, annotated_api_catalogue: None
):
    resp = test_client.get(
        f"/api/v1/devices/{MAST}/shots",
        params={"annotation": "confinement_mode:H-mode"},
    )
    assert resp.status_code == 200
    assert [s["id"] for s in resp.json()] == ["30421"]


def test_malformed_annotation_returns_422(
    test_client: TestClient, annotated_api_catalogue: None
):
    resp = test_client.get(
        f"/api/v1/devices/{MAST}/shots", params={"annotation": "disruption:"}
    )
    assert resp.status_code == 422


def test_datasets_filtered_by_shot_annotation(
    test_client: TestClient, annotated_api_catalogue: None
):
    """Use case: equilibrium datasets from ELMy MAST-U shots, in one request."""
    resp = test_client.get(
        f"/api/v1/devices/{MAST_U}/datasets",
        params={"name": "equilibrium", "shot_annotation": "elm"},
    )

    assert resp.status_code == 200
    assert [(d["name"], d["shot_id"]) for d in resp.json()] == [
        ("equilibrium", "50000")
    ]


def test_datasets_name_filter_without_annotations(
    test_client: TestClient, annotated_api_catalogue: None
):
    """Without shot_annotation, both shots' equilibrium datasets come back."""
    resp = test_client.get(
        f"/api/v1/devices/{MAST_U}/datasets", params={"name": "equilibrium"}
    )

    assert resp.status_code == 200
    assert sorted(d["shot_id"] for d in resp.json()) == ["50000", "50001"]
