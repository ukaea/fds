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
RIG = "RIG"

# Every test here reads from the seeded catalogue, so request it once for the
# module rather than as an unused argument on each test.
pytestmark = pytest.mark.usefixtures("annotated_catalogue")

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
# A coolant loop read by two thermocouples: a group can repeat inside a group.
COOLANT_HOT = ScientificProperty(
    name="coolant",
    properties=[
        ScientificProperty(name="type", value="water"),
        ScientificProperty(
            name="thermocouple",
            properties=[
                ScientificProperty(name="id", value="T1"),
                ScientificProperty(name="max", value=850, unit="°C"),
            ],
        ),
        ScientificProperty(
            name="thermocouple",
            properties=[
                ScientificProperty(name="id", value="T2"),
                ScientificProperty(name="max", value=400, unit="°C"),
            ],
        ),
    ],
)
COOLANT_COOL = ScientificProperty(
    name="coolant",
    properties=[
        ScientificProperty(name="type", value="water"),
        ScientificProperty(
            name="thermocouple",
            properties=[
                ScientificProperty(name="id", value="T1"),
                ScientificProperty(name="max", value=350, unit="°C"),
            ],
        ),
    ],
)
# The same name as the property inside `coolant`, but at the top level.
TOP_LEVEL_TYPE = ScientificProperty(name="type", value="water")


@pytest.fixture(name="annotated_catalogue")
def annotated_catalogue_fixture(
    session: Session, admin_user: AuthenticatedUser
) -> None:
    """Two devices, shots with and without annotations, and datasets under each shot."""
    devices = DeviceService(session)
    shots = ShotService(session)
    datasets = DatasetService(session)

    for device in (MAST, MAST_U, RIG):
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
        (RIG, "1001", [COOLANT_HOT]),
        (RIG, "1002", [COOLANT_COOL]),
        (RIG, "1003", [TOP_LEVEL_TYPE]),
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

    for shot_id in ("1001", "1003"):
        datasets.create(
            DatasetCreate(
                name="thermal",
                level=1,
                device_name=RIG,
                shot_id=shot_id,
                access_level=AccessLevel.PUBLIC,
                url=f"s3://data/{shot_id}/thermal.nc",
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
        s.id for s in shots.get_multi_by_device_name(device, properties=annotations)
    )


def test_use_case_mast_shots_that_disrupted(session: Session):
    assert shot_ids(ShotService(session), MAST, ["disruption"]) == ["30421"]


def test_use_case_equilibrium_datasets_from_elmy_shots(session: Session):
    results = DatasetService(session).get_datasets_for_device(
        MAST_U, name="equilibrium", shot_properties=["elm"]
    )
    assert [(d.name, d.shot_id) for d in results] == [("equilibrium", "50000")]


def test_presence_filter_ignores_value(session: Session):
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
def test_equality_filter(session: Session, annotation: str, expected: list[str]):
    assert shot_ids(ShotService(session), MAST, [annotation]) == expected


def test_boolean_value_matches_json_true(session: Session):
    """A query string "true" must match a stored JSON boolean."""
    assert shot_ids(ShotService(session), MAST, ["disruption:true"]) == ["30421"]


def test_repeated_annotations_are_anded(session: Session):
    shots = ShotService(session)
    assert shot_ids(shots, MAST, ["disruption", "elm"]) == ["30421"]
    # 30421 has the disruption, 30422 has L-mode; no shot has both.
    assert shot_ids(shots, MAST, ["disruption", "confinement_mode:L-mode"]) == []


def test_two_values_of_one_name_find_shots_matching_either(session: Session):
    """Values of one name widen the query rather than narrowing it.

    Selecting two values of one property in a filter means "either", which is
    what every faceted search does and what the catalogue conventions this
    follows do too. So all three annotated shots match: 30421 and 30422 held one
    mode each, and 30423 held both.

    Asking for a shot that carried *both* simultaneously, a transition, is a
    different and richer question. It belongs with the extent predicates in a
    structured search rather than in a query string, and is not expressible
    here.
    """
    either = ["confinement_mode:L-mode", "confinement_mode:H-mode"]
    assert shot_ids(ShotService(session), MAST, either) == ["30421", "30422", "30423"]


def test_different_names_still_narrow(session: Session):
    """Across names the query narrows, so the two readings cannot be confused."""
    shots = ShotService(session)
    assert shot_ids(shots, MAST, ["disruption", "elm"]) == ["30421"]


def test_presence_and_a_value_of_one_name_widen(session: Session):
    """A bare name under the same name as a value ORs with it: presence is
    satisfied by any entry, so it subsumes the value term."""
    mixed = ["confinement_mode", "confinement_mode:H-mode"]
    assert shot_ids(ShotService(session), MAST, mixed) == ["30421", "30422", "30423"]


def test_unknown_annotation_matches_nothing(session: Session):
    assert shot_ids(ShotService(session), MAST, ["sawtooth"]) == []


def test_null_scientific_metadata_does_not_error(session: Session):
    """Shot 30420 has NULL metadata; it must be skipped, not raise."""
    assert "30420" not in shot_ids(ShotService(session), MAST, ["disruption"])
    assert shot_ids(ShotService(session), MAST, None) == [
        "30420",
        "30421",
        "30422",
        "30423",
    ]


def test_filter_is_scoped_to_the_device(session: Session):
    """MAST 30421 and MAST-U 50000 both carry `elm`."""
    shots = ShotService(session)
    assert shot_ids(shots, MAST, ["elm"]) == ["30421"]
    assert shot_ids(shots, MAST_U, ["elm"]) == ["50000"]


def test_malformed_annotation_raises_validation_error(session: Session):
    with pytest.raises(FDSValidationError):
        ShotService(session).get_multi_by_device_name(MAST, properties=["disruption:"])


def test_shot_annotation_filter_excludes_datasets_with_no_shot(session: Session):
    """The device-level equilibrium dataset has no shot, so no shot annotations."""
    datasets = DatasetService(session)

    unfiltered = datasets.get_datasets_for_device(MAST_U, name="equilibrium")
    assert None in [d.shot_id for d in unfiltered]

    filtered = datasets.get_datasets_for_device(
        MAST_U, name="equilibrium", shot_properties=["elm"]
    )
    assert [d.shot_id for d in filtered] == ["50000"]


def test_dataset_name_and_device_filters(session: Session):
    datasets = DatasetService(session)

    by_name = datasets.get_multi(name="magnetics")
    assert {d.name for d in by_name} == {"magnetics"}
    assert len(by_name) == 2

    by_device = datasets.get_datasets_for_device(MAST)
    assert by_device == []


def test_dataset_own_annotations_are_independent_of_shot_annotations(
    session: Session, admin_user: AuthenticatedUser
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
    assert [d.name for d in datasets.get_multi(properties=["ufo"])] == ["camera"]
    assert datasets.get_multi(properties=["ufo"], shot_properties=["elm"]) == []


def test_a_path_matches_a_property_inside_a_group(session: Session):
    shots = ShotService(session)
    assert shot_ids(shots, RIG, ["coolant.type:water"]) == [
        "1001",
        "1002",
    ]


def test_a_path_names_one_place_in_the_tree(session: Session):
    """`type` at the top level and `type` inside `coolant` are different properties."""
    shots = ShotService(session)
    assert shot_ids(shots, RIG, ["type:water"]) == ["1003"]
    assert shot_ids(shots, RIG, ["thermocouple"]) == []


def test_a_path_reaches_a_group_inside_a_group(session: Session):
    shots = ShotService(session)
    assert shot_ids(shots, RIG, ["coolant.thermocouple.id:T2"]) == ["1001"]


def test_a_group_path_matches_records_carrying_the_group(session: Session):
    shots = ShotService(session)
    assert shot_ids(shots, RIG, ["coolant"]) == ["1001", "1002"]
    assert shot_ids(shots, RIG, ["coolant.thermocouple"]) == ["1001", "1002"]


def test_a_value_on_a_group_path_matches_nothing(session: Session):
    """A group has no value of its own to match."""
    shots = ShotService(session)
    assert shot_ids(shots, RIG, ["coolant:water"]) == []


def test_a_range_bound_on_a_path(session: Session):
    shots = ShotService(session)
    hot = shots.get_multi_by_device_name(RIG, minimums=["coolant.thermocouple.max:800"])
    cool = shots.get_multi_by_device_name(
        RIG, maximums=["coolant.thermocouple.max:380"]
    )
    assert [s.id for s in hot] == ["1001"]
    assert [s.id for s in cool] == ["1002"]


def test_conditions_on_one_group_are_met_by_one_instance(session: Session):
    """On 1001, T1 reached 850 and T2 only 400, so no thermocouple is T2 at 800."""
    shots = ShotService(session)
    t2_hot = shots.get_multi_by_device_name(
        RIG,
        properties=["coolant.thermocouple.id:T2"],
        minimums=["coolant.thermocouple.max:800"],
    )
    t1_hot = shots.get_multi_by_device_name(
        RIG,
        properties=["coolant.thermocouple.id:T1"],
        minimums=["coolant.thermocouple.max:800"],
    )
    assert [s.id for s in t2_hot] == []
    assert [s.id for s in t1_hot] == ["1001"]


def test_two_values_of_one_path_in_a_group_are_alternatives(session: Session):
    """A thermocouple that is T1 or T2, and that same thermocouple at 800."""
    shots = ShotService(session)
    either = ["coolant.thermocouple.id:T1", "coolant.thermocouple.id:T2"]
    either_hot = shots.get_multi_by_device_name(
        RIG, properties=either, minimums=["coolant.thermocouple.max:800"]
    )
    assert shot_ids(shots, RIG, either) == ["1001", "1002"]
    assert [s.id for s in either_hot] == ["1001"]


def test_a_condition_on_a_group_and_one_inside_it_meet_in_one_instance(
    session: Session,
):
    shots = ShotService(session).get_multi_by_device_name(
        RIG,
        properties=["coolant.type:water"],
        maximums=["coolant.thermocouple.max:380"],
    )
    assert [s.id for s in shots] == ["1002"]


def test_shot_property_follows_a_path(session: Session):
    results = DatasetService(session).get_datasets_for_device(
        RIG, shot_properties=["coolant.type:water"]
    )
    assert [(d.name, d.shot_id) for d in results] == [("thermal", "1001")]
