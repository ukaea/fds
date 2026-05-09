"""End-to-end tests for the NDJSON streaming export endpoints (ADR-0020).

Covers content-type, NDJSON line shape, per-row access filtering for
anonymous and authenticated callers, behaviour on broken inheritance
chains, and the empty-corpus 200-OK contract.
"""

import json

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.streaming import NDJSON_MEDIA_TYPE
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


def _parse_ndjson(body: str) -> list[dict]:
    """Parse an NDJSON body into a list of dicts. Tolerates the trailing newline."""
    return [json.loads(line) for line in body.splitlines() if line]


# ---------- /datasets/export ----------------------------------------------


def test_dataset_export_streams_ndjson(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="100", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    for i in range(5):
        DatasetService(session).create(
            DatasetCreate(
                name=f"ds_{i}",
                level=0,
                url=f"s3://bucket/{i}",
                device_name="MAST",
                shot_id="100",
                access_level=AccessLevel.PUBLIC,
            ),
            user=admin_user,
        )
    session.commit()

    response = test_client.get("/api/v1/datasets/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(NDJSON_MEDIA_TYPE)

    rows = _parse_ndjson(response.text)
    assert len(rows) == 5
    assert {r["name"] for r in rows} == {f"ds_{i}" for i in range(5)}
    # Every row is a parseable JSON object on its own line.
    assert response.text.endswith("\n")


def test_dataset_export_filters_restricted_for_anonymous(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="100", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="public_ds",
            level=0,
            url="s3://bucket/public",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="embargoed_ds",
            level=0,
            url="s3://bucket/embargoed",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.EMBARGOED,
        ),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="restricted_ds",
            level=0,
            url="s3://bucket/restricted",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/datasets/export")
    assert response.status_code == 200
    rows = _parse_ndjson(response.text)
    names = {r["name"] for r in rows}
    # Anonymous sees PUBLIC + EMBARGOED metadata only.
    assert names == {"public_ds", "embargoed_ds"}


def test_dataset_export_admin_sees_all(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    admin_user_token: dict,
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="100", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="restricted_ds",
            level=0,
            url="s3://bucket/restricted",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/datasets/export", headers=admin_user_token)
    assert response.status_code == 200
    rows = _parse_ndjson(response.text)
    assert {r["name"] for r in rows} == {"restricted_ds"}


def test_dataset_export_anonymous_with_only_restricted_returns_200_empty(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="100", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="restricted_ds",
            level=0,
            url="s3://bucket/restricted",
            device_name="MAST",
            shot_id="100",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/datasets/export")
    assert response.status_code == 200
    assert response.text == ""


def test_dataset_export_no_data_returns_200_empty(test_client: TestClient):
    response = test_client.get("/api/v1/datasets/export")
    assert response.status_code == 200
    assert response.text == ""


def test_dataset_export_filters_by_device_name(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    DeviceService(session).create(DeviceCreate(name="JET", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(
        ShotCreate(device_name="JET", id="1", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="mast_ds",
            level=0,
            url="s3://m",
            device_name="MAST",
            shot_id="1",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="jet_ds",
            level=0,
            url="s3://j",
            device_name="JET",
            shot_id="1",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/datasets/export?device_name=MAST")
    assert response.status_code == 200
    rows = _parse_ndjson(response.text)
    assert {r["name"] for r in rows} == {"mast_ds"}


def test_dataset_export_filters_by_shot_id(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="2", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="ds1",
            level=0,
            url="s3://1",
            device_name="MAST",
            shot_id="1",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="ds2",
            level=0,
            url="s3://2",
            device_name="MAST",
            shot_id="2",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/datasets/export?device_name=MAST&shot_id=1")
    rows = _parse_ndjson(response.text)
    assert {r["name"] for r in rows} == {"ds1"}


def test_dataset_export_handles_orphaned_dataset_safely(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """A dataset whose enclosing shot has been deleted falls back to the
    ``DEFAULT_ACCESS_LEVEL = RESTRICTED``; an anonymous caller's stream
    silently drops it without raising."""
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    DatasetService(session).create(
        DatasetCreate(
            name="orphan",
            level=0,
            url="s3://o",
            device_name="MAST",
            shot_id="1",
            # No explicit access_level; will inherit.
        ),
        admin_user,
    )
    session.commit()

    # Drop the underlying shot row via raw SQL to leave the dataset with a
    # dangling FK (bypassing the ORM's cascade). Using exec_driver_sql on the
    # raw connection avoids SQLModel's deprecated session.execute() path while
    # still allowing the literal DELETE that session.exec() does not accept.
    session.connection().exec_driver_sql("DELETE FROM shot WHERE id = '1'")
    session.commit()

    response = test_client.get("/api/v1/datasets/export")
    assert response.status_code == 200
    rows = _parse_ndjson(response.text)
    # Anonymous + RESTRICTED-by-fallback → row hidden, but no exception raised.
    assert rows == []


# ---------- /devices/{device_name}/shots/export ---------------------------


def test_shot_export_streams_for_device(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    for i in range(3):
        ShotService(session).create(
            ShotCreate(device_name="MAST", id=str(i), access_level=AccessLevel.PUBLIC),
            admin_user,
        )
    session.commit()

    response = test_client.get("/api/v1/devices/MAST/shots/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(NDJSON_MEDIA_TYPE)
    rows = _parse_ndjson(response.text)
    assert {r["id"] for r in rows} == {"0", "1", "2"}


def test_shot_export_filters_restricted_for_anonymous(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        admin_user,
    )
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="2", access_level=AccessLevel.RESTRICTED),
        admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/devices/MAST/shots/export")
    rows = _parse_ndjson(response.text)
    assert {r["id"] for r in rows} == {"1"}


# ---------- /collections/export -------------------------------------------


def test_collection_export_streams_flat_records(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    for i in range(3):
        CollectionService(session).create(
            CollectionCreate(
                name=f"col_{i}",
                device_name="MAST",
                access_level=AccessLevel.PUBLIC,
            ),
            admin_user,
        )
    session.commit()

    response = test_client.get("/api/v1/collections/export?device_name=MAST")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(NDJSON_MEDIA_TYPE)
    rows = _parse_ndjson(response.text)
    assert {r["name"] for r in rows} == {"col_0", "col_1", "col_2"}
    # Flat metadata only — no inlined members or children.
    for r in rows:
        assert "datasets" not in r or r["datasets"] is None
        assert "child_collections" not in r or r["child_collections"] is None


def test_collection_export_filters_restricted_for_anonymous(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), admin_user)
    CollectionService(session).create(
        CollectionCreate(
            name="public_col",
            device_name="MAST",
            access_level=AccessLevel.PUBLIC,
        ),
        admin_user,
    )
    CollectionService(session).create(
        CollectionCreate(
            name="restricted_col",
            device_name="MAST",
            access_level=AccessLevel.RESTRICTED,
        ),
        admin_user,
    )
    session.commit()

    response = test_client.get("/api/v1/collections/export")
    rows = _parse_ndjson(response.text)
    assert {r["name"] for r in rows} == {"public_col"}
