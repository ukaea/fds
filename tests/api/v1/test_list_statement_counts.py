from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


@contextmanager
def statements(session: Session) -> Iterator[list[str]]:
    """The SQL statements ``session`` issues inside the block.

    Savepoints are left out: they are this suite's rollback, not the request's.
    """
    issued: list[str] = []

    def record(conn, cursor, statement, *args):
        if not statement.startswith(("SAVEPOINT", "RELEASE SAVEPOINT")):
            issued.append(statement)

    bind = session.get_bind()
    event.listen(bind, "before_cursor_execute", record)
    try:
        yield issued
    finally:
        event.remove(bind, "before_cursor_execute", record)


@pytest.fixture
def catalogue(session: Session, admin_user: AuthenticatedUser) -> int:
    """A public device with 4 shots of 3 datasets each, and a collection
    holding a collection for each shot. Returns the parent collection's id."""
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
    for shot in range(4):
        ShotService(session).create(
            ShotCreate(id=str(shot), device_name="MAST"), admin_user
        )
        for n in range(3):
            DatasetService(session).create(
                DatasetCreate(
                    name=f"d{n}",
                    level=1,
                    device_name="MAST",
                    shot_id=str(shot),
                    url=f"s3://bucket/{shot}/{n}.zarr",
                ),
                admin_user,
            )
        child = collections.create(
            CollectionCreate(name=f"run{shot}", device_name="MAST", shot_id=str(shot)),
            admin_user,
        )
        assert child.id is not None
        collections.add_child_collection(parent_id, child.id, admin_user)
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
        ("/v1/devices/MAST/shots", {}),
        ("/v1/devices/MAST/shots", {"include_device": True}),
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
