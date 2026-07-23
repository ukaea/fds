from datetime import datetime

import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.reference import ReferenceCoverage
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

DEVICE = "MAST"
SHOT = "150"


@pytest.fixture(name="datasets")
def datasets_fixture(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture(name="mast_shot")
def mast_shot_fixture(session: Session, admin_user: AuthenticatedUser) -> None:
    """Create the MAST device and shot 150."""
    DeviceService(session).create(DeviceCreate(name=DEVICE, type="Tokamak"), admin_user)
    ShotService(session).create(
        ShotCreate(id=SHOT, device_name=DEVICE, shot_at=datetime(2008, 6, 1)),
        admin_user,
    )


@pytest.fixture(name="make_version")
def make_version_fixture(
    session: Session,
    datasets: DatasetService,
    admin_user: AuthenticatedUser,
    mast_shot: None,
):
    """Create a public device-level geometry version and commit."""

    def make(name: str, roles: list[str], coverage: ReferenceCoverage):
        version = datasets.create(
            DatasetCreate(
                name=name,
                level=0,
                device_name=DEVICE,
                geometry_roles=roles,
                applies_to=coverage,
                access_level=AccessLevel.PUBLIC,
                url=f"s3://geometry/{name}.nc",
            ),
            admin_user,
        )
        session.commit()
        return version

    return make


@pytest.fixture(name="make_signal")
def make_signal_fixture(
    session: Session,
    datasets: DatasetService,
    admin_user: AuthenticatedUser,
    mast_shot: None,
):
    """Create a public shot-level signal referencing ``references`` and commit."""

    def make(references: list[str], *, name: str = "Te"):
        signal = datasets.create(
            DatasetCreate(
                name=name,
                level=2,
                device_name=DEVICE,
                shot_id=SHOT,
                geometry_references=references,
                access_level=AccessLevel.PUBLIC,
                url="s3://signals/te.zarr",
            ),
            admin_user,
        )
        session.commit()
        return signal

    return make
