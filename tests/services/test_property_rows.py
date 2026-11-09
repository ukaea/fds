from decimal import Decimal

import pytest
from sqlmodel import Session, col, select, text

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.property_rows import CollectionProperty, DatasetProperty, ShotProperty
from app.models.scientific_metadata import Extent, ScientificProperty
from app.models.shot import ShotCreate, ShotUpdate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

RIG = "RIG"

NBI = ScientificProperty(
    name="nbi",
    extent=Extent(dimension="time", start=0.1, end=0.3, unit="s"),
    properties=[
        ScientificProperty(
            name="beam",
            properties=[
                ScientificProperty(name="source", value="SS"),
                ScientificProperty(name="power", value=1.6, unit="MW"),
            ],
        ),
        ScientificProperty(
            name="beam",
            properties=[
                ScientificProperty(name="source", value="SW"),
                ScientificProperty(name="power", value="1.4", unit="MW"),
            ],
        ),
    ],
)
GAS = ScientificProperty(name="gas", value="D2")


@pytest.fixture(name="shots")
def shots_fixture(session: Session, admin_user: AuthenticatedUser) -> ShotService:
    DeviceService(session).create(
        DeviceCreate(name=RIG, type="Tokamak", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    return ShotService(session)


def add_shot(
    shots: ShotService,
    user: AuthenticatedUser,
    metadata: list[ScientificProperty],
) -> None:
    shots.create(
        ShotCreate(
            id="1001",
            device_name=RIG,
            access_level=AccessLevel.PUBLIC,
            scientific_metadata=metadata,
        ),
        user,
    )


def rows(session: Session) -> list[tuple]:
    return [
        (row.position, row.path, row.is_group, row.value, row.number, row.dimension)
        for row in session.exec(
            select(ShotProperty)
            .where(ShotProperty.shot == "1001")
            .order_by(col(ShotProperty.position))
        )
    ]


def test_a_row_for_every_property_at_every_depth(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    add_shot(shots, admin_user, [ScientificProperty(name="fault", value=None), NBI])
    assert rows(session) == [
        ((0,), "fault", False, None, None, None),
        ((1,), "nbi", True, None, None, "time"),
        ((1, 0), "nbi.beam", True, None, None, "time"),
        ((1, 0, 0), "nbi.beam.source", False, "SS", None, "time"),
        ((1, 0, 1), "nbi.beam.power", False, 1.6, Decimal("1.6"), "time"),
        ((1, 1), "nbi.beam", True, None, None, "time"),
        ((1, 1, 0), "nbi.beam.source", False, "SW", None, "time"),
        ((1, 1, 1), "nbi.beam.power", False, "1.4", Decimal("1.4"), "time"),
    ]


def test_a_number_too_large_to_hold_is_not_a_number(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    add_shot(shots, admin_user, [ScientificProperty(name="note", value="1e200000")])
    assert rows(session) == [((0,), "note", False, "1e200000", None, None)]


def test_writing_the_metadata_replaces_the_rows(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    add_shot(shots, admin_user, [NBI])
    shots.update(
        shot_id="1001",
        device_name=RIG,
        obj_in=ShotUpdate(scientific_metadata=[GAS]),
        user=admin_user,
    )
    assert rows(session) == [((0,), "gas", False, "D2", None, None)]


def test_a_write_outside_fds_replaces_the_rows(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    add_shot(shots, admin_user, [NBI])
    session.connection().execute(
        text(
            "UPDATE shot SET scientific_metadata = "
            """'[{"name": "gas", "value": "D2"}]' WHERE id = '1001'"""
        )
    )
    assert rows(session) == [((0,), "gas", False, "D2", None, None)]


def test_deleting_a_shot_deletes_its_rows(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    add_shot(shots, admin_user, [NBI])
    shots.delete("1001", admin_user, RIG)
    assert rows(session) == []


def test_datasets_and_collections_have_rows_of_their_own(
    session: Session, shots: ShotService, admin_user: AuthenticatedUser
):
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="thermal",
            device_name=RIG,
            access_level=AccessLevel.PUBLIC,
            scientific_metadata=[GAS],
            url="s3://data/thermal.nc",
        ),
        admin_user,
    )
    collection = CollectionService(session).create(
        CollectionCreate(name="campaign", scientific_metadata=[GAS]), admin_user
    )

    def paths(table, key):
        return session.exec(select(table.path).where(key)).all()

    assert paths(DatasetProperty, DatasetProperty.dataset == dataset.id) == ["gas"]
    assert paths(
        CollectionProperty, CollectionProperty.collection == collection.id
    ) == ["gas"]
