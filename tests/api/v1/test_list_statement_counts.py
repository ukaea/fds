from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.coverage import Coverage, ShotRange
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService
from tests.conftest import statements


@pytest.fixture
def catalogue(session: Session, admin_user: AuthenticatedUser) -> int:
    """A public device with 4 shots of 3 datasets each, and a collection
    holding a collection for each shot. Each shot and dataset has an annotation
    of its own, and two device-level annotations cover shot ranges. Every
    dataset references a calibrated geometry. Returns the parent collection's
    id."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    collections = CollectionService(session)
    parent = collections.create(
        CollectionCreate(name="runs", access_level=AccessLevel.PUBLIC), admin_user
    )
    parent_id = parent.id
    assert parent_id is not None
    subjects = []
    for shot in range(4):
        ShotService(session).create(
            ShotCreate(
                id=str(shot),
                device_name="MAST",
                shot_at=datetime(2016, 8, 3, tzinfo=UTC) + timedelta(hours=shot),
            ),
            admin_user,
        )
        DatasetService(session).create(
            DatasetCreate(
                name="elm-times",
                level=1,
                device_name="MAST",
                shot_id=str(shot),
                annotates="elm",
            ),
            admin_user,
        )
        for n in range(3):
            dataset = DatasetService(session).create(
                DatasetCreate(
                    name=f"d{n}",
                    level=1,
                    device_name="MAST",
                    shot_id=str(shot),
                    url=f"s3://bucket/{shot}/{n}.zarr",
                    geometry_references=["coils"],
                    calibration_references=["gain"],
                ),
                admin_user,
            )
            subjects.append(dataset)
        child = collections.create(
            CollectionCreate(name=f"run{shot}", device_name="MAST", shot_id=str(shot)),
            admin_user,
        )
        assert child.id is not None
        collections.add_child_collection(parent_id, child.id, admin_user)
    for name, shots in (("deadregion", ("0", "2")), ("coil-fault", ("1", "3"))):
        DatasetService(session).create(
            DatasetCreate(
                name=name,
                level=1,
                device_name="MAST",
                annotates=name,
                applies_to=Coverage(
                    shot_ranges=[ShotRange(from_shot=shots[0], to_shot=shots[1])]
                ),
            ),
            admin_user,
        )
    every_shot = Coverage(shot_ranges=[ShotRange(from_shot="0", to_shot="3")])
    DatasetService(session).create(
        DatasetCreate(
            name="coil-geometry",
            level=1,
            device_name="MAST",
            geometry_roles=["coils"],
            calibration_references=["gain"],
            applies_to=every_shot,
        ),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="gain-calibration",
            level=1,
            device_name="MAST",
            calibration_roles=["gain"],
            calibration_stage=1,
            applies_to=every_shot,
        ),
        admin_user,
    )
    for subject in subjects:
        DatasetService(session).create(
            DatasetCreate(
                name=f"{subject.name}-mask",
                level=1,
                device_name="MAST",
                shot_id=subject.shot_id,
                annotates="ufo",
                subject_dataset_id=subject.id,
            ),
            admin_user,
        )
    session.commit()
    # A request starts with an empty session; one left holding the seeded rows
    # would answer from memory and hide the queries.
    session.expunge_all()
    return parent_id


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/datasets", {}),
        ("/v1/devices/MAST/datasets", {}),
        ("/v1/devices/MAST/datasets", {"include_geometry": True}),
        ("/v1/devices/MAST/datasets", {"include_calibration": True}),
        ("/v1/devices/MAST/datasets", {"include_annotations": True}),
        ("/v1/devices/MAST/shots", {}),
        ("/v1/devices/MAST/shots", {"include_device": True}),
        ("/v1/devices/MAST/shots", {"include_annotations": True}),
        ("/v1/collections/{parent}/collections", {}),
    ],
)
def test_listing_issues_the_same_statements_whatever_the_page_size(
    test_client: TestClient,
    session: Session,
    catalogue: int,
    path: str,
    params: dict[str, Any],
):
    url = path.format(parent=catalogue)
    with statements(session) as small:
        assert len(test_client.get(url, params={**params, "limit": 2}).json()) == 2
    session.expunge_all()
    with statements(session) as large:
        assert len(test_client.get(url, params={**params, "limit": 4}).json()) == 4

    assert len(large) == len(small)


def test_reading_annotations_issues_the_same_statements_whatever_their_number(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(ShotCreate(id="1", device_name="MAST"), admin_user)
    datasets = DatasetService(session)
    subjects = []
    for count in (1, 5):
        subject = datasets.create(
            DatasetCreate(
                name=f"camera{count}", level=1, device_name="MAST", shot_id="1"
            ),
            admin_user,
        )
        for n in range(count):
            datasets.create(
                DatasetCreate(
                    name=f"mask{count}-{n}",
                    level=1,
                    device_name="MAST",
                    shot_id="1",
                    annotates="ufo",
                    subject_dataset_id=subject.id,
                ),
                admin_user,
            )
        subjects.append(subject.id)
    session.commit()
    session.expunge_all()

    issued = []
    for subject_id, count in zip(subjects, (1, 5), strict=True):
        with statements(session) as read:
            response = test_client.get(
                f"/v1/datasets/id/{subject_id}", params={"include_annotations": True}
            )
        assert len(response.json()["annotations"]) == count
        issued.append(len(read))
        session.expunge_all()

    assert issued[0] == issued[1]
