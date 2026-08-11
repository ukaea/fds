"""Feature-annotation resolution, frame-scoped."""

from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.models.coverage import Coverage
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.annotation_service import AnnotationService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.jsonld import map_dataset_to_dcat, map_shot_to_dcat
from app.services.shot_service import ShotService

_SHOT_AT = datetime(2016, 8, 3, 14, 32, tzinfo=timezone.utc)


@pytest.fixture(name="device_service")
def _device_service(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def _shot_service(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="dataset_service")
def _dataset_service(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture(name="scene")
def _scene(device_service, shot_service, dataset_service, admin_user):
    """A device, a shot, a signal dataset, and one annotation per frame."""
    device_service.create(DeviceCreate(name="DEV"), user=admin_user)
    shot_service.create(
        ShotCreate(id="100", device_name="DEV", shot_at=_SHOT_AT), user=admin_user
    )
    shot_service.create(ShotCreate(id="500", device_name="DEV"), user=admin_user)

    def make(name: str, level: int = 2, **fields):
        return dataset_service.create(
            DatasetCreate(
                name=name,
                level=level,
                device_name="DEV",
                access_level=AccessLevel.PUBLIC,
                **fields,
            ),
            user=admin_user,
        )

    signal = make("camera", shot_id="100", level=1)
    return {
        "signal": signal,
        # dataset frame: subject is a specific dataset (lives in the shot too)
        "dataset_frame": make(
            "ufo-mask", shot_id="100", annotates="ufo", subject_dataset_id=signal.id
        ),
        # shot frame: belongs to the shot, no dataset subject
        "shot_frame": make("elm-times", shot_id="100", annotates="elm"),
        # device frame: device-level, coverage includes shot 100
        "device_frame": make(
            "deadregion",
            annotates="deadregion",
            applies_to=Coverage(shots=["100"]),
        ),
    }


def test_dataset_frame_resolves_on_its_dataset(dataset_service, scene, session):
    annotations = AnnotationService(session).for_dataset(scene["signal"])
    assert [a.name for a in annotations] == ["ufo-mask"]


def test_shot_frame_and_device_frame_resolve_on_the_shot(shot_service, scene, session):
    shot = shot_service.get(("DEV", "100"))
    names = {a.name for a in AnnotationService(session).for_shot(shot)}
    assert names == {"elm-times", "deadregion"}
    # No cross-surfacing: the dataset-frame annotation does not leak into shot frame.
    assert "ufo-mask" not in names


def test_device_frame_coverage_excludes_uncovered_shot(shot_service, scene, session):
    shot = shot_service.get(("DEV", "500"))
    # 500 is not covered by the dead-region and has no shot-frame annotation.
    assert AnnotationService(session).for_shot(shot) == []


def test_include_annotations_on_dataset_read(dataset_service, scene):
    read = dataset_service.to_read_model(scene["signal"], include_annotations=True)
    assert read.annotations is not None
    assert [a.name for a in read.annotations] == ["ufo-mask"]


def test_include_annotations_on_shot_read(shot_service, scene):
    read = shot_service.to_read_model(
        shot_service.get(("DEV", "100")), include_annotations=True
    )
    assert read.annotations is not None
    assert {a.name for a in read.annotations} == {"elm-times", "deadregion"}


def test_no_annotations_resolved_by_default(dataset_service, shot_service, scene):
    assert dataset_service.to_read_model(scene["signal"]).annotations is None
    assert (
        shot_service.to_read_model(shot_service.get(("DEV", "100"))).annotations is None
    )


def test_dataset_jsonld_emits_annotation_qualified_relation(dataset_service, scene):
    read = dataset_service.to_read_model(scene["signal"], include_annotations=True)
    doc = map_dataset_to_dcat(read, "http://testserver", annotations=read.annotations)
    relations = doc["dcat:qualifiedRelation"]
    assert len(relations) == 1
    assert relations[0]["@type"] == "dcat:Relationship"
    assert relations[0]["dcat:hadRole"]["@id"] == "fuel:annotation"


def test_shot_jsonld_emits_annotation_qualified_relations(shot_service, scene):
    read = shot_service.to_read_model(
        shot_service.get(("DEV", "100")), include_annotations=True
    )
    doc = map_shot_to_dcat(read, "http://testserver", annotations=read.annotations)
    relations = doc["dcat:qualifiedRelation"]
    # shot-frame (elm-times) + device-frame (deadregion)
    assert len(relations) == 2
    assert all(r["dcat:hadRole"]["@id"] == "fuel:annotation" for r in relations)
