from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityType
from app.models.coverage import Coverage, ShotRange
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.activity_service import ActivityService
from app.services.annotation_service import AnnotationService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.jsonld import map_dataset_to_dcat, map_shot_to_dcat
from app.services.shot_service import ShotService
from tests.conftest import resource

_SHOT_AT = datetime(2016, 8, 3, 14, 32, tzinfo=UTC)


@pytest.fixture(name="shot_service")
def _shot_service(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="dataset_service")
def _dataset_service(session: Session) -> DatasetService:
    return DatasetService(session)


def _make_public_dataset(
    dataset_service: DatasetService,
    admin: AuthenticatedUser,
    name: str,
    level: int = 2,
    **fields,
):
    return dataset_service.create(
        DatasetCreate(
            name=name,
            level=level,
            device_name="DEV",
            access_level=AccessLevel.PUBLIC,
            **fields,
        ),
        user=admin,
    )


def _make_team_dataset(
    dataset_service: DatasetService, admin: AuthenticatedUser, name: str, **fields
):
    return dataset_service.create(
        DatasetCreate(
            name=name,
            device_name="DEV",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["dev_team"],
            **fields,
        ),
        user=admin,
    )


def _scene(session: Session, admin_user: AuthenticatedUser) -> dict:
    """A device, a shot, a signal dataset, and one annotation attached to each
    of the dataset, the shot and the device."""
    dataset_service = DatasetService(session)
    shot_service = ShotService(session)
    DeviceService(session).create(DeviceCreate(name="DEV"), user=admin_user)
    shot_service.create(
        ShotCreate(id="100", device_name="DEV", shot_at=_SHOT_AT), user=admin_user
    )
    shot_service.create(ShotCreate(id="500", device_name="DEV"), user=admin_user)

    signal = _make_public_dataset(
        dataset_service, admin_user, "camera", shot_id="100", level=1
    )
    return {
        "signal": signal,
        # dataset frame: subject is a specific dataset (lives in the shot too)
        "dataset_frame": _make_public_dataset(
            dataset_service,
            admin_user,
            "ufo-mask",
            shot_id="100",
            annotates="ufo",
            subject_dataset=signal.id,
        ),
        # shot frame: belongs to the shot, no dataset subject
        "shot_frame": _make_public_dataset(
            dataset_service, admin_user, "elm-times", shot_id="100", annotates="elm"
        ),
        # device frame: device-level, coverage includes shot 100
        "device_frame": _make_public_dataset(
            dataset_service,
            admin_user,
            "deadregion",
            annotates="deadregion",
            applies_to=Coverage(shots=["100"]),
        ),
    }


def test_dataset_frame_resolves_on_its_dataset(session, admin_user):
    scene = _scene(session, admin_user)
    [annotations] = AnnotationService(session).for_datasets(
        [scene["signal"]], user=admin_user
    )
    assert [a.name for a in annotations] == ["ufo-mask"]


def test_shot_frame_and_device_frame_resolve_on_the_shot(
    shot_service, session, admin_user
):
    _scene(session, admin_user)
    shot = shot_service.get(("DEV", "100"))
    [annotations] = AnnotationService(session).for_shots([shot], user=admin_user)
    names = {a.name for a in annotations}
    assert names == {"elm-times", "deadregion"}
    # No cross-surfacing: the dataset-frame annotation does not leak into shot frame.
    assert "ufo-mask" not in names


def test_device_frame_coverage_excludes_uncovered_shot(
    shot_service, session, admin_user
):
    _scene(session, admin_user)
    shot = shot_service.get(("DEV", "500"))
    # 500 is not covered by the dead-region and has no shot-frame annotation.
    assert AnnotationService(session).for_shots([shot], user=admin_user) == [[]]


def test_a_replaced_annotation_is_left_out(
    dataset_service, shot_service, session, admin_user
):
    scene = _scene(session, admin_user)
    correction = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.ANALYSIS), user=admin_user
    )
    _make_public_dataset(
        dataset_service,
        admin_user,
        "elm-times",
        shot_id="100",
        annotates="elm",
        activity_id=correction.id,
        replaces=[scene["shot_frame"].id],
    )

    [annotations] = AnnotationService(session).for_shots(
        [shot_service.get(("DEV", "100"))], user=admin_user
    )

    elm = [a for a in annotations if a.name == "elm-times"]
    assert [a.activity_id for a in elm] == [correction.id]


def test_an_annotation_stays_for_a_reader_who_cannot_read_its_replacement(
    dataset_service, shot_service, session, admin_user
):
    scene = _scene(session, admin_user)
    correction = ActivityService(session).create(
        ActivityCreate(activity_type=ActivityType.ANALYSIS), user=admin_user
    )
    dataset_service.create(
        DatasetCreate(
            name="elm-times",
            level=2,
            device_name="DEV",
            shot_id="100",
            annotates="elm",
            access_level=AccessLevel.RESTRICTED,
            activity_id=correction.id,
            replaces=[scene["shot_frame"].id],
        ),
        user=admin_user,
    )
    shot = shot_service.get(("DEV", "100"))

    as_public = shot_service.to_read_model(shot, include_annotations=True)
    as_admin = shot_service.to_read_model(
        shot, include_annotations=True, user=admin_user
    )

    assert [a.id for a in as_public.annotations or [] if a.name == "elm-times"] == [
        scene["shot_frame"].id
    ]
    assert [
        a.activity_id for a in as_admin.annotations or [] if a.name == "elm-times"
    ] == [correction.id]


def test_include_annotations_on_dataset_read(dataset_service, session, admin_user):
    scene = _scene(session, admin_user)
    read = dataset_service.to_read_model(scene["signal"], include_annotations=True)
    assert read.annotations is not None
    assert [a.name for a in read.annotations] == ["ufo-mask"]


def test_include_annotations_on_shot_read(shot_service, session, admin_user):
    _scene(session, admin_user)
    read = shot_service.to_read_model(
        shot_service.get(("DEV", "100")), include_annotations=True
    )
    assert read.annotations is not None
    assert {a.name for a in read.annotations} == {"elm-times", "deadregion"}


def test_device_frame_annotation_resolves_on_every_shot_it_covers(
    dataset_service, shot_service, admin_user, session
):
    _scene(session, admin_user)
    shot_service.create(
        ShotCreate(id="101", device_name="DEV", shot_at=_SHOT_AT + timedelta(hours=1)),
        user=admin_user,
    )
    _make_public_dataset(
        dataset_service,
        admin_user,
        "coil-fault",
        annotates="fault",
        applies_to=Coverage(shot_ranges=[ShotRange(from_shot="100", to_shot="101")]),
    )
    shots = [shot_service.get(("DEV", shot_id)) for shot_id in ("100", "101", "500")]

    reads = shot_service.to_read_models(shots, include_annotations=True)

    assert [{a.name for a in read.annotations or []} for read in reads] == [
        {"elm-times", "deadregion", "coil-fault"},
        {"coil-fault"},
        set(),
    ]


def test_no_annotations_resolved_by_default(
    dataset_service, shot_service, session, admin_user
):
    scene = _scene(session, admin_user)
    assert dataset_service.to_read_model(scene["signal"]).annotations is None
    assert (
        shot_service.to_read_model(shot_service.get(("DEV", "100"))).annotations is None
    )


def test_dataset_jsonld_emits_annotation_qualified_relation(
    dataset_service, session, admin_user
):
    scene = _scene(session, admin_user)
    read = dataset_service.to_read_model(scene["signal"], include_annotations=True)
    doc = resource(
        map_dataset_to_dcat(read, "http://testserver", annotations=read.annotations)
    )
    relations = doc["dcat:qualifiedRelation"]
    assert len(relations) == 1
    assert relations[0]["@type"] == "dcat:Relationship"
    assert relations[0]["dcat:hadRole"]["@id"] == "fuel:annotation"


def test_shot_jsonld_emits_annotation_qualified_relations(
    shot_service, session, admin_user
):
    _scene(session, admin_user)
    read = shot_service.to_read_model(
        shot_service.get(("DEV", "100")), include_annotations=True
    )
    doc = resource(
        map_shot_to_dcat(read, "http://testserver", annotations=read.annotations)
    )
    relations = doc["dcat:qualifiedRelation"]
    # shot-frame (elm-times) + device-frame (deadregion)
    assert len(relations) == 2
    assert all(r["dcat:hadRole"]["@id"] == "fuel:annotation" for r in relations)


def test_annotations_resolved_only_where_readable(
    dataset_service, shot_service, admin_user, session
):
    scene = _scene(session, admin_user)
    _make_team_dataset(
        dataset_service,
        admin_user,
        "ufo-review",
        shot_id="100",
        annotates="ufo",
        subject_dataset=scene["signal"].id,
    )
    _make_team_dataset(
        dataset_service, admin_user, "elm-review", shot_id="100", annotates="elm"
    )
    shot = shot_service.get(("DEV", "100"))

    dataset_read = dataset_service.to_read_model(
        scene["signal"], include_annotations=True
    )
    shot_read = shot_service.to_read_model(shot, include_annotations=True)
    shot_doc = resource(
        shot_service.to_dcat(shot, "http://testserver", include_annotations=True)
    )

    assert [a.name for a in dataset_read.annotations or []] == ["ufo-mask"]
    assert {a.name for a in shot_read.annotations or []} == {"elm-times", "deadregion"}
    assert len(shot_doc["dcat:qualifiedRelation"]) == 2
    team_read = shot_service.to_read_model(
        shot,
        include_annotations=True,
        user=AuthenticatedUser(id="member", scopes=("dev_team",)),
    )
    assert "elm-review" in {a.name for a in team_read.annotations or []}
