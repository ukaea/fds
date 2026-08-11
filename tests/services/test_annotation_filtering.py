import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.scientific_metadata import Extent, ScientificProperty
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import FDSValidationError
from app.services.shot_service import ShotService

MAST = "MAST"
MAST_U = "MAST-U"

H_MODE = ScientificProperty(
    name="confinement_mode",
    value="H-mode",
    extent=Extent(dimension="time", start=0.20, end=0.45, unit="s"),
)
DISRUPTION = ScientificProperty(
    name="disruption",
    value=True,
    extent=Extent(dimension="time", start=0.606, unit="s"),
)
ELM = ScientificProperty(name="elm", value="type-I")
L_MODE = ScientificProperty(name="confinement_mode", value="L-mode")
# A shot that transitioned: the same property twice, at different values, over
# different windows. Nothing stops scientific_metadata repeating a name, and a
# discharge that goes L-mode, H-mode, back to L-mode is the ordinary case.
L_MODE_EARLY = ScientificProperty(
    name="confinement_mode",
    value="L-mode",
    extent=Extent(dimension="time", start=0.05, end=0.18, unit="s"),
)
H_MODE_LATE = ScientificProperty(
    name="confinement_mode",
    value="H-mode",
    extent=Extent(dimension="time", start=0.18, end=0.40, unit="s"),
)


@pytest.fixture(name="annotated_catalogue")
def annotated_catalogue_fixture(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """Two devices, shots with and without annotations, and datasets under each shot."""
    devices = DeviceService(session)
    shots = ShotService(session)
    datasets = DatasetService(session)

    for device in (MAST, MAST_U):
        devices.create(
            DeviceCreate(name=device, type="Tokamak", access_level=AccessLevel.PUBLIC),
            admin_user,
        )

    for device, shot_id, metadata in [
        (MAST, "30420", None),  # unannotated: scientific_metadata is NULL
        (MAST, "30421", [H_MODE, DISRUPTION, ELM]),
        (MAST, "30422", [L_MODE]),
        (MAST, "30423", [L_MODE_EARLY, H_MODE_LATE]),
        (MAST_U, "50000", [ELM]),
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

    # A device-level dataset with no shot: must never match a shot_annotations filter.
    datasets.create(
        DatasetCreate(
            name="equilibrium",
            level=0,
            device_name=MAST_U,
            access_level=AccessLevel.PUBLIC,
            url="s3://data/reference/equilibrium.nc",
        ),
        admin_user,
    )
    session.commit()


def shot_ids(
    shots: ShotService, device: str, annotations: list[str] | None
) -> list[str]:
    return sorted(
        s.id for s in shots.get_multi_by_device_name(device, annotations=annotations)
    )


def test_use_case_mast_shots_that_disrupted(
    session: Session, annotated_catalogue: None
):
    assert shot_ids(ShotService(session), MAST, ["disruption"]) == ["30421"]


def test_use_case_equilibrium_datasets_from_elmy_shots(
    session: Session, annotated_catalogue: None
):
    results = DatasetService(session).get_datasets_for_device(
        MAST_U, name="equilibrium", shot_annotations=["elm"]
    )
    assert [(d.name, d.shot_id) for d in results] == [("equilibrium", "50000")]


def test_presence_filter_ignores_value(session: Session, annotated_catalogue: None):
    """`confinement_mode` is present on both H-mode and L-mode shots."""
    assert shot_ids(ShotService(session), MAST, ["confinement_mode"]) == [
        "30421",
        "30422",
        "30423",
    ]


@pytest.mark.parametrize(
    ("annotation", "expected"),
    [
        ("confinement_mode:H-mode", ["30421", "30423"]),
        ("confinement_mode:L-mode", ["30422", "30423"]),
        ("elm:type-I", ["30421"]),
        ("elm:type-III", []),
    ],
)
def test_equality_filter(
    session: Session, annotated_catalogue: None, annotation: str, expected: list[str]
):
    assert shot_ids(ShotService(session), MAST, [annotation]) == expected


def test_boolean_value_matches_json_true(session: Session, annotated_catalogue: None):
    """A query string "true" must match a stored JSON boolean."""
    assert shot_ids(ShotService(session), MAST, ["disruption:true"]) == ["30421"]


def test_repeated_annotations_are_anded(session: Session, annotated_catalogue: None):
    shots = ShotService(session)
    assert shot_ids(shots, MAST, ["disruption", "elm"]) == ["30421"]
    # 30421 has the disruption, 30422 has L-mode; no shot has both.
    assert shot_ids(shots, MAST, ["disruption", "confinement_mode:L-mode"]) == []


def test_two_values_of_one_name_find_shots_that_had_both(
    session: Session, annotated_catalogue: None
):
    """Each annotation gets its own EXISTS, so ANDing two values of one property
    asks for a record carrying both entries, not for one entry holding two values.

    That is the query for a transition: 30423 was in L-mode and later in H-mode,
    so it matches; 30421 and 30422 held one mode each and do not.
    """
    both = ["confinement_mode:L-mode", "confinement_mode:H-mode"]
    assert shot_ids(ShotService(session), MAST, both) == ["30423"]


def test_unknown_annotation_matches_nothing(
    session: Session, annotated_catalogue: None
):
    assert shot_ids(ShotService(session), MAST, ["sawtooth"]) == []


def test_null_scientific_metadata_does_not_error(
    session: Session, annotated_catalogue: None
):
    """Shot 30420 has NULL metadata; it must be skipped, not raise."""
    assert "30420" not in shot_ids(ShotService(session), MAST, ["disruption"])
    assert shot_ids(ShotService(session), MAST, None) == [
        "30420",
        "30421",
        "30422",
        "30423",
    ]


def test_filter_is_scoped_to_the_device(session: Session, annotated_catalogue: None):
    """MAST 30421 and MAST-U 50000 both carry `elm`."""
    shots = ShotService(session)
    assert shot_ids(shots, MAST, ["elm"]) == ["30421"]
    assert shot_ids(shots, MAST_U, ["elm"]) == ["50000"]


def test_malformed_annotation_raises_validation_error(
    session: Session, annotated_catalogue: None
):
    with pytest.raises(FDSValidationError):
        ShotService(session).get_multi_by_device_name(MAST, annotations=["disruption:"])


def test_shot_annotation_filter_excludes_datasets_with_no_shot(
    session: Session, annotated_catalogue: None
):
    """The device-level equilibrium dataset has no shot, so no shot annotations."""
    datasets = DatasetService(session)

    unfiltered = datasets.get_datasets_for_device(MAST_U, name="equilibrium")
    assert None in [d.shot_id for d in unfiltered]

    filtered = datasets.get_datasets_for_device(
        MAST_U, name="equilibrium", shot_annotations=["elm"]
    )
    assert [d.shot_id for d in filtered] == ["50000"]


def test_dataset_name_and_device_filters(session: Session, annotated_catalogue: None):
    datasets = DatasetService(session)

    by_name = datasets.get_multi(name="magnetics")
    assert {d.name for d in by_name} == {"magnetics"}
    assert len(by_name) == 2

    by_device = datasets.get_datasets_for_device(MAST)
    assert by_device == []


def test_dataset_own_annotations_are_independent_of_shot_annotations(
    session: Session, admin_user: AuthenticatedUser, annotated_catalogue: None
):
    """`annotation` filters the dataset's own metadata, `shot_annotation` its parent shot's."""
    datasets = DatasetService(session)
    datasets.create(
        DatasetCreate(
            name="camera",
            level=2,
            device_name=MAST_U,
            shot_id="50001",
            access_level=AccessLevel.PUBLIC,
            scientific_metadata=[ScientificProperty(name="ufo", value=True)],
            url="s3://data/50001/camera.nc",
        ),
        admin_user,
    )
    session.commit()

    # The dataset carries `ufo`; its shot (50001) carries no annotations at all.
    assert [d.name for d in datasets.get_multi(annotations=["ufo"])] == ["camera"]
    assert datasets.get_multi(annotations=["ufo"], shot_annotations=["elm"]) == []
