"""Predicate-purity tests for ``is_accessible`` (ADR-0020).

The streaming export depends on these predicates returning a bool and never
raising — anything raised inside a streaming generator after response
headers are sent cannot be turned into a graceful HTTP error.
"""

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.identity import ANONYMOUS_USER
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

ADMIN = AuthenticatedUser(id="admin", scopes=("fds-admin",))


def _seed(session: Session) -> None:
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), ADMIN)
    ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        ADMIN,
    )
    session.commit()


@pytest.mark.parametrize(
    "level,expected_anonymous",
    [
        (AccessLevel.PUBLIC, True),
        (AccessLevel.EMBARGOED, True),  # metadata is discoverable
        (AccessLevel.RESTRICTED, False),
    ],
)
def test_dataset_is_accessible_returns_bool_per_access_level(
    session: Session, level: AccessLevel, expected_anonymous: bool
):
    _seed(session)
    service = DatasetService(session)
    dataset = service.create(
        DatasetCreate(
            name="ds",
            level=0,
            url="s3://b",
            device_name="MAST",
            shot_id="1",
            access_level=level,
        ),
        ADMIN,
    )
    session.commit()

    result = service.is_accessible(dataset, ANONYMOUS_USER)
    assert isinstance(result, bool)
    assert result is expected_anonymous


def test_dataset_is_accessible_admin_sees_restricted(session: Session):
    _seed(session)
    service = DatasetService(session)
    dataset = service.create(
        DatasetCreate(
            name="ds",
            level=0,
            url="s3://b",
            device_name="MAST",
            shot_id="1",
            access_level=AccessLevel.RESTRICTED,
        ),
        ADMIN,
    )
    session.commit()

    assert service.is_accessible(dataset, ADMIN) is True


@pytest.mark.parametrize(
    "level,expected_anonymous",
    [
        (AccessLevel.PUBLIC, True),
        (AccessLevel.EMBARGOED, False),  # ShotService treats EMBARGOED as auth-required
        (AccessLevel.RESTRICTED, False),
    ],
)
def test_shot_is_accessible_returns_bool(
    session: Session, level: AccessLevel, expected_anonymous: bool
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), ADMIN)
    shot = ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=level), ADMIN
    )
    session.commit()

    result = ShotService(session).is_accessible(shot, ANONYMOUS_USER)
    assert isinstance(result, bool)
    assert result is expected_anonymous


@pytest.mark.parametrize(
    "level,expected_anonymous",
    [
        (AccessLevel.PUBLIC, True),
        (AccessLevel.EMBARGOED, True),
        (AccessLevel.RESTRICTED, False),
    ],
)
def test_collection_is_accessible_returns_bool(
    session: Session, level: AccessLevel, expected_anonymous: bool
):
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), ADMIN)
    collection = CollectionService(session).create(
        CollectionCreate(name="c", device_name="MAST", access_level=level), ADMIN
    )
    session.commit()

    result = CollectionService(session).is_accessible(collection, ANONYMOUS_USER)
    assert isinstance(result, bool)
    assert result is expected_anonymous


def test_predicates_never_raise_on_orphaned_inheritance(session: Session):
    """When an inherited parent is missing, the access-level walk falls back
    to ``DEFAULT_ACCESS_LEVEL = RESTRICTED``. The predicate must reflect that
    by returning ``False`` for an anonymous caller — never raise."""
    DeviceService(session).create(DeviceCreate(name="MAST", type="Tokamak"), ADMIN)
    shot = ShotService(session).create(
        ShotCreate(device_name="MAST", id="1", access_level=AccessLevel.PUBLIC),
        ADMIN,
    )
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="ds", level=0, url="s3://b", device_name="MAST", shot_id="1"
        ),
        ADMIN,
    )
    session.commit()

    # Drop the shot to break the inheritance chain.
    session.delete(shot)
    session.commit()
    session.refresh(dataset)

    # Should not raise; should return False (RESTRICTED fallback for anonymous).
    result = DatasetService(session).is_accessible(dataset, ANONYMOUS_USER)
    assert result is False
