from datetime import datetime

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.reference import ReferenceCoverage
from app.models.shot import ShotCreate, ShotUpdate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.reference_service import GEOMETRY, ReferenceService
from app.services.shot_service import ShotService

DEVICE = "MAST"

# Shot ids mapped to shot_at; the timeline drives range and date matching.
SHOT_TIMES = {
    "100": datetime(2008, 1, 1),
    "150": datetime(2008, 6, 1),
    "200": datetime(2009, 1, 1),
    "201": datetime(2009, 1, 2),
    "300": datetime(2010, 1, 1),
}


@pytest.fixture(name="datasets")
def datasets_fixture(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture(name="shots")
def shots_fixture(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="geometry")
def geometry_fixture(session: Session) -> ReferenceService:
    return ReferenceService(session, GEOMETRY)


@pytest.fixture(name="device")
def device_fixture(session: Session, admin_user: AuthenticatedUser) -> None:
    """Create the MAST device, the SHOT_TIMES timeline, and one undated shot."""
    DeviceService(session).create(DeviceCreate(name=DEVICE, type="Tokamak"), admin_user)
    shots = ShotService(session)
    for shot_id, shot_at in SHOT_TIMES.items():
        shots.create(
            ShotCreate(id=shot_id, device_name=DEVICE, shot_at=shot_at), admin_user
        )
    shots.create(ShotCreate(id="undated", device_name=DEVICE), admin_user)


@pytest.fixture(name="make_version")
def make_version_fixture(datasets: DatasetService, admin_user: AuthenticatedUser):
    """Create a MAST geometry version; pass ``shot_id`` to make it shot-level."""

    def make(
        name: str,
        roles: list[str],
        coverage: ReferenceCoverage,
        *,
        shot_id: str | None = None,
    ):
        return datasets.create(
            DatasetCreate(
                name=name,
                level=0,
                device_name=DEVICE,
                shot_id=shot_id,
                geometry_roles=roles,
                applies_to=coverage,
                url=f"s3://geometry/{name}.nc",
            ),
            user=admin_user,
        )

    return make


@pytest.fixture(name="make_global_version")
def make_global_version_fixture(
    datasets: DatasetService, admin_user: AuthenticatedUser
):
    """Create a global (no-device) geometry version."""

    def make(name: str, roles: list[str], coverage: ReferenceCoverage):
        return datasets.create(
            DatasetCreate(
                name=name,
                level=0,
                geometry_roles=roles,
                applies_to=coverage,
                url=f"s3://geometry/{name}.nc",
            ),
            user=admin_user,
        )

    return make


@pytest.fixture(name="make_signal")
def make_signal_fixture(datasets: DatasetService, admin_user: AuthenticatedUser):
    """Create a shot-level MAST signal referencing ``references``."""

    def make(references: list[str], *, shot_id: str = "150", name: str = "Te"):
        return datasets.create(
            DatasetCreate(
                name=name,
                level=2,
                device_name=DEVICE,
                shot_id=shot_id,
                geometry_references=references,
                url="s3://signals/te.zarr",
            ),
            user=admin_user,
        )

    return make


@pytest.fixture(name="get_shot")
def get_shot_fixture(shots: ShotService):
    """Look up a MAST shot by id."""

    def get(shot_id: str):
        return shots.get((DEVICE, shot_id))

    return get


@pytest.fixture(name="update_shot")
def update_shot_fixture(shots: ShotService, admin_user: AuthenticatedUser):
    """Update a MAST shot's fields."""

    def update(shot_id: str, **fields):
        return shots.update(
            shot_id=shot_id,
            device_name=DEVICE,
            obj_in=ShotUpdate(**fields),
            user=admin_user,
        )

    return update


@pytest.fixture(name="delete_shot")
def delete_shot_fixture(shots: ShotService, admin_user: AuthenticatedUser):
    """Delete a MAST shot."""

    def delete(shot_id: str):
        return shots.delete(shot_id, user=admin_user, device_name=DEVICE)

    return delete
