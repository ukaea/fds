import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


@pytest.fixture
def device_service(session: Session):
    return DeviceService(session)


@pytest.fixture
def shot_service(session: Session):
    return ShotService(session)


@pytest.fixture
def dataset_service(session: Session):
    return DatasetService(session)


def test_access_inheritance_dataset_from_shot(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (RESTRICTED default) -> Shot (PUBLIC override) -> Dataset (Inherit)
    device_service.create(DeviceCreate(name="TOKAMAK"), user=admin_user)
    shot = shot_service.create(
        ShotCreate(id="SHOT-1", device_name="TOKAMAK", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    dataset = dataset_service.create(
        DatasetCreate(name="data", level=1, data_url="url", shot_id=shot.id),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.access_level is None
    assert read_model.effective_access_level == AccessLevel.PUBLIC


def test_access_inheritance_dataset_from_device(
    device_service: DeviceService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (EMBARGOED override) -> Dataset (Inherit, device context)
    device_service.create(
        DeviceCreate(name="SECRET-LAB", access_level=AccessLevel.EMBARGOED),
        user=admin_user,
    )
    dataset = dataset_service.create(
        DatasetCreate(
            name="top-secret", level=1, data_url="url", device_name="SECRET-LAB"
        ),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.effective_access_level == AccessLevel.EMBARGOED


def test_access_inheritance_global_default(
    dataset_service: DatasetService, admin_user: AuthenticatedUser
):
    # Setup: Global Dataset -> Inherit (RESTRICTED default)
    dataset = dataset_service.create(
        DatasetCreate(name="global-data", level=1, data_url="url"), user=admin_user
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.effective_access_level == AccessLevel.RESTRICTED


def test_access_override_at_dataset_level(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (RESTRICTED) -> Shot (RESTRICTED) -> Dataset (EMBARGOED override)
    device_service.create(DeviceCreate(name="DEV"), user=admin_user)
    shot = shot_service.create(ShotCreate(id="S1", device_name="DEV"), user=admin_user)
    dataset = dataset_service.create(
        DatasetCreate(
            name="override",
            level=1,
            data_url="url",
            shot_id=shot.id,
            access_level=AccessLevel.EMBARGOED,
        ),
        user=admin_user,
    )

    read_model = dataset_service.to_read_model(dataset)
    assert read_model.access_level == AccessLevel.EMBARGOED
    assert read_model.effective_access_level == AccessLevel.EMBARGOED


def test_shot_inherits_from_device(
    device_service: DeviceService,
    shot_service: ShotService,
    admin_user: AuthenticatedUser,
):
    # Setup: Device (PUBLIC) -> Shot (Inherit)
    device_service.create(
        DeviceCreate(name="OPEN-DEV", access_level=AccessLevel.PUBLIC),
        user=admin_user,
    )
    shot = shot_service.create(
        ShotCreate(id="S2", device_name="OPEN-DEV"), user=admin_user
    )

    read_model = shot_service.to_read_model(shot)
    assert read_model.effective_access_level == AccessLevel.PUBLIC
