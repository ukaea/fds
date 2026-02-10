import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.datasetsource import DatasetSourceCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate
from app.services.dataset_service import DatasetService
from app.services.datasetsource_service import DatasetSourceService
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


@pytest.fixture(name="datasetsource_service")
def datasetsource_service_fixture(session: Session) -> DatasetSourceService:
    return DatasetSourceService(session)


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
    dataset1 = dataset_service.create(
        DatasetCreate(
            name="Data 1",
            level=1,
            data_url="url1",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )
    dataset2 = dataset_service.create(
        DatasetCreate(
            name="Data 2",
            level=1,
            data_url="url2",
            shot_id=shot.id,
            device_name="Test Device",
        ),
        user=admin_user,
    )
    source1 = source_service.create(SourceCreate(name="Source 1"), user=admin_user)
    source2 = source_service.create(SourceCreate(name="Source 2"), user=admin_user)
    return shot, dataset1, dataset2, source1, source2


def test_create_datasetsource_link(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, _, source1, _ = setup_data
    link_create = DatasetSourceCreate(dataset_id=dataset1.id, source_id=source1.id)
    link = datasetsource_service.create(link_create, user=admin_user)
    assert link is not None
    assert link.dataset_id == dataset1.id
    assert link.source_id == source1.id


def test_get_datasetsource_link(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, _, source1, _ = setup_data
    link_create = DatasetSourceCreate(dataset_id=dataset1.id, source_id=source1.id)
    datasetsource_service.create(link_create, user=admin_user)

    retrieved_link = datasetsource_service.get(
        dataset_id=dataset1.id, source_id=source1.id
    )
    assert retrieved_link is not None
    assert retrieved_link.dataset_id == dataset1.id
    assert retrieved_link.source_id == source1.id


def test_get_datasetsource_link_not_found(
    datasetsource_service: DatasetSourceService,
):
    retrieved_link = datasetsource_service.get(dataset_id=999, source_id=999)
    assert retrieved_link is None


def test_delete_datasetsource_link(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, _, source1, _ = setup_data
    link_create = DatasetSourceCreate(dataset_id=dataset1.id, source_id=source1.id)
    datasetsource_service.create(link_create, user=admin_user)

    deleted = datasetsource_service.delete_with_auth(
        dataset_id=dataset1.id, source_id=source1.id, user=admin_user
    )
    assert deleted is True

    retrieved_link = datasetsource_service.get(
        dataset_id=dataset1.id, source_id=source1.id
    )
    assert retrieved_link is None


def test_delete_datasetsource_link_not_found(
    datasetsource_service: DatasetSourceService, admin_user: AuthenticatedUser
):
    with pytest.raises(ResourceNotFoundError):
        datasetsource_service.delete_with_auth(
            dataset_id=999, source_id=999, user=admin_user
        )


def test_get_links_for_dataset(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, _, source1, source2 = setup_data
    datasetsource_service.create(
        DatasetSourceCreate(dataset_id=dataset1.id, source_id=source1.id),
        user=admin_user,
    )
    datasetsource_service.create(
        DatasetSourceCreate(dataset_id=dataset1.id, source_id=source2.id),
        user=admin_user,
    )

    links = datasetsource_service.get_for_dataset(dataset_id=dataset1.id)
    assert len(links) == 2
    assert all(link.dataset_id == dataset1.id for link in links)


def test_get_links_for_source(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, dataset2, source1, _ = setup_data
    datasetsource_service.create(
        DatasetSourceCreate(dataset_id=dataset1.id, source_id=source1.id),
        user=admin_user,
    )
    datasetsource_service.create(
        DatasetSourceCreate(dataset_id=dataset2.id, source_id=source1.id),
        user=admin_user,
    )

    links = datasetsource_service.get_for_source(source_id=source1.id)
    assert len(links) == 2
    assert all(link.source_id == source1.id for link in links)


def test_create_datasetsource_with_metadata(
    datasetsource_service: DatasetSourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset1, _, source1, _ = setup_data
    link_create = DatasetSourceCreate(
        dataset_id=dataset1.id,
        source_id=source1.id,
        source_version="v1.2.3",
        activity_type="SIMULATION",
        parameters={"dt": 0.01, "nodes": 100},
    )
    link = datasetsource_service.create(link_create, user=admin_user)
    assert link.source_version == "v1.2.3"
    assert link.activity_type == "SIMULATION"
    assert link.parameters == {"dt": 0.01, "nodes": 100}
