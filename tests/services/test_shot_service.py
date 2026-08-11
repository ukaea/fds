from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import Shot, ShotCreate, ShotUpdate
from app.services.device_service import DeviceService
from app.services.exceptions import (
    DeviceNotFoundError,
    FDSValidationError,
    ForbiddenError,
)
from app.services.shot_service import ShotService

IDP_A = "https://idp-a.example.com"


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


def test_create_shot_for_device(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    # Using global admin
    shot_create = ShotCreate(id="shot-101", device_name="Test Device")
    shot = shot_service.create(shot_create, admin_user)
    assert shot is not None
    assert shot.id == "shot-101"
    assert shot.device_name == "test device"


def test_create_shot_with_device_scope(
    device_service: DeviceService,
    shot_service: ShotService,
    mast_admin_user: AuthenticatedUser,
    admin_user: AuthenticatedUser,
):
    # Device name matches scope "mast_admin"
    device_service.create(DeviceCreate(name="MAST", type="Test"), user=admin_user)

    shot_create = ShotCreate(id="mast-shot", device_name="MAST")
    shot = shot_service.create(shot_create, mast_admin_user)
    assert shot.id == "mast-shot"


def test_create_shot_unauthorized(
    device_service: DeviceService,
    shot_service: ShotService,
    mast_admin_user: AuthenticatedUser,
    admin_user: AuthenticatedUser,
):
    # User has mast_admin but trying to create for JET
    device_service.create(DeviceCreate(name="JET", type="Test"), user=admin_user)

    shot_create = ShotCreate(id="jet-shot", device_name="JET")
    with pytest.raises(ForbiddenError):
        shot_service.create(shot_create, mast_admin_user)


def test_create_shot_for_nonexistent_device(
    shot_service: ShotService, admin_user: AuthenticatedUser
):
    shot_create = ShotCreate(id="shot-102", device_name="Nonexistent")
    with pytest.raises(DeviceNotFoundError):
        shot_service.create(shot_create, admin_user)


def test_get_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device = device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    assert device.id is not None

    created_shot = shot_service.create(
        ShotCreate(id="shot-201", device_name="Test Device"), admin_user
    )
    assert created_shot is not None

    retrieved_shot = shot_service.get(("Test Device", created_shot.id))
    assert retrieved_shot is not None
    assert retrieved_shot.id == "shot-201"


def test_get_shots_for_device(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="Device 1", type="A"), user=admin_user)
    device_service.create(DeviceCreate(name="Device 2", type="B"), user=admin_user)

    shot_service.create(ShotCreate(id="shot-1001", device_name="Device 1"), admin_user)
    shot_service.create(ShotCreate(id="shot-1002", device_name="Device 1"), admin_user)
    shot_service.create(ShotCreate(id="shot-2001", device_name="Device 2"), admin_user)

    # Get shots for device 1
    device1_shots = shot_service.get_multi_by_device_name("Device 1", user=admin_user)
    assert len(device1_shots) == 2
    assert all(shot.device_name == "device 1" for shot in device1_shots)
    assert {shot.id for shot in device1_shots} == {"shot-1001", "shot-1002"}


def test_delete_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    session: Session,
    admin_user: AuthenticatedUser,
):
    device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )

    shot_to_delete = shot_service.create(
        ShotCreate(id="shot-301", device_name="Test Device"), admin_user
    )
    assert shot_to_delete is not None

    shot_service.delete(shot_to_delete.id, admin_user, device_name="Test Device")

    db_shot = session.get(Shot, ("Test Device", shot_to_delete.id))
    assert db_shot is None


def test_delete_shot_unauthorized(
    device_service: DeviceService,
    shot_service: ShotService,
    mast_admin_user: AuthenticatedUser,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="JET", type="Test"), user=admin_user)

    shot_to_delete = shot_service.create(
        ShotCreate(id="shot-302", device_name="JET"), admin_user
    )
    assert shot_to_delete is not None

    with pytest.raises(ForbiddenError):
        shot_service.delete(shot_to_delete.id, mast_admin_user, device_name="JET")


@pytest.mark.usefixtures("idp_config")
def test_create_shot_public_with_required_scopes_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEV"), user=admin_user)
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        shot_service.create(
            ShotCreate(
                id="s1",
                device_name="DEV",
                access_level=AccessLevel.PUBLIC,
                required_scopes=["some:scope"],
            ),
            user=admin_user,
        )


@pytest.mark.usefixtures("idp_config")
def test_create_shot_null_access_with_allowed_idps_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEV2"), user=admin_user)
    with pytest.raises(FDSValidationError, match="allowed_idps requires"):
        shot_service.create(
            ShotCreate(id="s2", device_name="DEV2", allowed_idps=[IDP_A]),
            user=admin_user,
        )


@pytest.mark.usefixtures("idp_config")
def test_create_shot_restricted_with_policy_accepted(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEV3"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(
            id="s3",
            device_name="DEV3",
            access_level=AccessLevel.RESTRICTED,
            allowed_idps=[IDP_A],
        ),
        user=admin_user,
    )
    assert shot.id == "s3"
    assert shot.allowed_idps == [IDP_A]


@pytest.mark.usefixtures("idp_config")
def test_update_shot_transition_to_public_with_scopes_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEV4"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(
            id="s4",
            device_name="DEV4",
            access_level=AccessLevel.RESTRICTED,
            required_scopes=["some:scope"],
        ),
        user=admin_user,
    )
    with pytest.raises(FDSValidationError, match="PUBLIC"):
        shot_service.update(
            shot_id=shot.id,
            device_name="DEV4",
            obj_in=ShotUpdate(access_level=AccessLevel.PUBLIC),
            user=admin_user,
        )


_T0 = datetime(2024, 3, 15, 14, 32, tzinfo=timezone.utc)
_T5 = datetime(2024, 3, 15, 14, 37, tzinfo=timezone.utc)  # +300s


def test_create_shot_consistent_temporal(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEVT"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(
            id="t-ok",
            device_name="DEVT",
            shot_at=_T0,
            shot_end=_T5,
            shot_duration=300.0,
        ),
        user=admin_user,
    )
    assert shot.shot_duration == 300.0
    # Persisted datetimes round-trip as naive (SQLite drops tzinfo).
    assert shot.shot_end is not None
    assert shot.shot_end.replace(tzinfo=timezone.utc) == _T5


def test_create_shot_records_t0_at_distinct_from_shot_at(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    """t0_at (the relative time base zero) is stored and may differ from shot_at."""
    device_service.create(DeviceCreate(name="DEVT0"), user=admin_user)
    t0 = datetime(
        2024, 3, 15, 14, 32, 6, tzinfo=timezone.utc
    )  # breakdown, +6s of shot_at
    shot = shot_service.create(
        ShotCreate(id="t-t0", device_name="DEVT0", shot_at=_T0, t0_at=t0),
        user=admin_user,
    )
    assert shot.t0_at is not None
    # Persisted datetimes round-trip as naive (SQLite drops tzinfo).
    assert shot.t0_at.replace(tzinfo=timezone.utc) == t0
    assert shot.t0_at != shot.shot_at


def test_create_shot_duration_only(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    """Under-determined combinations are allowed (no contradiction)."""
    device_service.create(DeviceCreate(name="DEVT2"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="t-dur", device_name="DEVT2", shot_at=_T0, shot_duration=300.0),
        user=admin_user,
    )
    assert shot.shot_end is None
    assert shot.shot_duration == 300.0


def test_create_shot_inconsistent_duration_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEVT3"), user=admin_user)
    with pytest.raises(FDSValidationError, match="inconsistent"):
        shot_service.create(
            ShotCreate(
                id="t-bad",
                device_name="DEVT3",
                shot_at=_T0,
                shot_end=_T5,
                shot_duration=999.0,
            ),
            user=admin_user,
        )


def test_create_shot_end_before_start_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEVT4"), user=admin_user)
    with pytest.raises(FDSValidationError, match="before"):
        shot_service.create(
            ShotCreate(id="t-rev", device_name="DEVT4", shot_at=_T5, shot_end=_T0),
            user=admin_user,
        )


def test_create_shot_end_without_start_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEVT5"), user=admin_user)
    with pytest.raises(FDSValidationError, match="requires shot_at"):
        shot_service.create(
            ShotCreate(id="t-noend", device_name="DEVT5", shot_end=_T5),
            user=admin_user,
        )


def test_create_shot_negative_duration_rejected(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    device_service.create(DeviceCreate(name="DEVT6"), user=admin_user)
    with pytest.raises(FDSValidationError, match="negative"):
        shot_service.create(
            ShotCreate(id="t-neg", device_name="DEVT6", shot_duration=-1.0),
            user=admin_user,
        )


def test_update_shot_temporal_consistency_against_existing(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    """Update is validated against the merged (existing + patch) state."""
    device_service.create(DeviceCreate(name="DEVT7"), user=admin_user)
    shot_service.create(
        ShotCreate(id="t-upd", device_name="DEVT7", shot_at=_T0),
        user=admin_user,
    )

    with pytest.raises(FDSValidationError, match="before"):
        shot_service.update(
            shot_id="t-upd",
            device_name="DEVT7",
            obj_in=ShotUpdate(
                shot_end=datetime(2024, 3, 15, 14, 0, tzinfo=timezone.utc)
            ),
            user=admin_user,
        )
