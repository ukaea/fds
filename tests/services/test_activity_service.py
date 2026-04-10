import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import ActivityCreate, ActivityUpdate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import ResourceNotFoundError
from app.services.shot_service import ShotService
from app.services.source_service import SourceService


@pytest.fixture(name="device_service")
def device_service_fixture(session: Session) -> DeviceService:
    return DeviceService(session)


@pytest.fixture(name="shot_service")
def shot_service_fixture(session: Session) -> ShotService:
    return ShotService(session)


@pytest.fixture(name="dataset_service")
def dataset_service_fixture(session: Session) -> DatasetService:
    return DatasetService(session)


@pytest.fixture(name="source_service")
def source_service_fixture(session: Session) -> SourceService:
    return SourceService(session)


@pytest.fixture(name="activity_service")
def activity_service_fixture(session: Session) -> ActivityService:
    return ActivityService(session)


@pytest.fixture(name="setup_data")
def setup_data_fixture(
    device_service: DeviceService,
    shot_service: ShotService,
    dataset_service: DatasetService,
    source_service: SourceService,
    admin_user: AuthenticatedUser,
):
    device_service.create(
        DeviceCreate(name="Test Device", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="shot-1", device_name="Test Device"), user=admin_user
    )
    dataset = dataset_service.create(
        DatasetCreate(
            name="Data 1",
            level=1,
            url="url1",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )
    source1 = source_service.create(SourceCreate(name="Source 1"), user=admin_user)
    source2 = source_service.create(SourceCreate(name="Source 2"), user=admin_user)
    return shot, dataset, source1, source2


def test_create_activity(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=source1.id, activity_type="SIMULATION"),
        user=admin_user,
    )
    assert activity is not None
    assert activity.id is not None
    assert activity.source_id == source1.id
    assert activity.activity_type == "SIMULATION"


def test_create_activity_with_metadata(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(
            source_id=source1.id,
            activity_type="SIMULATION",
            source_version="v1.2.3",
            parameters={"dt": 0.01, "nodes": 100},
        ),
        user=admin_user,
    )
    assert activity.source_version == "v1.2.3"
    assert activity.activity_type == "SIMULATION"
    assert activity.parameters == {"dt": 0.01, "nodes": 100}


def test_create_activity_invalid_source(
    activity_service: ActivityService,
    admin_user: AuthenticatedUser,
):
    with pytest.raises(ResourceNotFoundError):
        activity_service.create(ActivityCreate(source_id=9999), user=admin_user)


def test_get_activity(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    created = activity_service.create(
        ActivityCreate(source_id=source1.id), user=admin_user
    )
    retrieved = activity_service.get(created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.source_id == source1.id


def test_get_activity_not_found(activity_service: ActivityService):
    assert activity_service.get(9999) is None


def test_update_activity(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=source1.id, activity_type="MEASUREMENT"),
        user=admin_user,
    )
    assert activity.id is not None
    updated = activity_service.update(
        id=activity.id,
        obj_in=ActivityUpdate(activity_type="SIMULATION", source_version="v2.0"),
        user=admin_user,
    )
    assert updated.activity_type == "SIMULATION"
    assert updated.source_version == "v2.0"


def test_delete_activity(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=source1.id), user=admin_user
    )
    assert activity.id is not None
    deleted = activity_service.delete(activity.id, user=admin_user)
    assert deleted is True
    assert activity_service.get(activity.id) is None


def test_delete_activity_not_found(
    activity_service: ActivityService,
    admin_user: AuthenticatedUser,
):
    with pytest.raises(ResourceNotFoundError):
        activity_service.delete(9999, user=admin_user)


def test_get_for_source(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, source2 = setup_data
    activity_service.create(ActivityCreate(source_id=source1.id), user=admin_user)
    activity_service.create(ActivityCreate(source_id=source1.id), user=admin_user)
    activity_service.create(ActivityCreate(source_id=source2.id), user=admin_user)

    results = activity_service.get_for_source(source1.id)
    assert len(results) == 2
    assert all(a.source_id == source1.id for a in results)


def test_multiple_datasets_share_activity(
    activity_service: ActivityService,
    dataset_service: DatasetService,
    device_service: DeviceService,
    shot_service: ShotService,
    source_service: SourceService,
    session: Session,
    admin_user: AuthenticatedUser,
):
    """A single Activity can be referenced by multiple Datasets."""
    device_service.create(
        DeviceCreate(name="shared-device", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="s1", device_name="shared-device"), user=admin_user
    )
    source = source_service.create(SourceCreate(name="pipeline"), user=admin_user)
    assert source.id is not None
    activity = activity_service.create(
        ActivityCreate(source_id=source.id, activity_type="MEASUREMENT"),
        user=admin_user,
    )

    ds1 = dataset_service.create(
        DatasetCreate(
            name="ds1",
            level=0,
            url="s3://a",
            shot_id=shot.id,
            device_name="shared-device",
            activity_id=activity.id,
        ),
        user=admin_user,
    )
    ds2 = dataset_service.create(
        DatasetCreate(
            name="ds2",
            level=0,
            url="s3://b",
            shot_id=shot.id,
            device_name="shared-device",
            activity_id=activity.id,
        ),
        user=admin_user,
    )

    assert ds1.activity_id == activity.id
    assert ds2.activity_id == activity.id
