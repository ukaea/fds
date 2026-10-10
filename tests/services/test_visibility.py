from sqlmodel import Session

from app.models.activity import ActivityCreate, ActivityType
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.activity_service import ActivityService
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

TEAM = AuthenticatedUser(id="member", scopes=("dev_team",))
PUBLIC = AccessLevel.PUBLIC
RESTRICTED = AccessLevel.RESTRICTED

# Public, public, team-only, team-only, public, public: the team-only pair sits
# where a page boundary falls when paging by two.
LEVELS = [PUBLIC, PUBLIC, RESTRICTED, RESTRICTED, PUBLIC, PUBLIC]


def _setup(session: Session, admin: AuthenticatedUser) -> None:
    DeviceService(session).create(
        DeviceCreate(name="DEV", type="Tokamak", access_level=PUBLIC), user=admin
    )
    ShotService(session).create(
        ShotCreate(id="1", device_name="DEV", access_level=PUBLIC), user=admin
    )


def _policy(level: AccessLevel) -> dict:
    if level is RESTRICTED:
        return {"access_level": RESTRICTED, "required_scopes": ["dev_team"]}
    return {"access_level": level}


def _make_datasets(
    session: Session, admin: AuthenticatedUser, shot_id: str | None = None
) -> list[int]:
    ids = []
    for i, level in enumerate(LEVELS):
        dataset = DatasetService(session).create(
            DatasetCreate(
                name=f"ds{i}", device_name="DEV", shot_id=shot_id, **_policy(level)
            ),
            user=admin,
        )
        assert dataset.id is not None
        ids.append(dataset.id)
    return ids


def _make_collections(session: Session, admin: AuthenticatedUser) -> list[int]:
    ids = []
    for i, level in enumerate(LEVELS):
        collection = CollectionService(session).create(
            CollectionCreate(name=f"col{i}", device_name="DEV", **_policy(level)),
            user=admin,
        )
        assert collection.id is not None
        ids.append(collection.id)
    return ids


def _ids(rows) -> list[int]:
    return [row.id for row in rows]


def _public(ids: list[int]) -> list[int]:
    return [i for i, level in zip(ids, LEVELS, strict=True) if level is PUBLIC]


def test_device_datasets_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user)
    service = DatasetService(session)

    pages = [
        _ids(
            service.get_datasets_for_device(
                "DEV", ANONYMOUS_USER, offset=offset, limit=2
            )
        )
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_shot_datasets_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user, shot_id="1")
    service = DatasetService(session)

    pages = [
        _ids(
            service.get_datasets_for_shot(
                "1", "DEV", ANONYMOUS_USER, offset=offset, limit=2
            )
        )
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_global_datasets_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user)
    service = DatasetService(session)

    pages = [
        _ids(service.get_multi(ANONYMOUS_USER, offset=offset, limit=2))
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_device_collections_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_collections(session, admin_user)
    service = CollectionService(session)

    pages = [
        _ids(
            service.get_collections_for_device(
                "DEV", ANONYMOUS_USER, offset=offset, limit=2
            )
        )
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_collection_members_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user)
    service = CollectionService(session)
    parent = service.create(
        CollectionCreate(name="parent", access_level=PUBLIC), user=admin_user
    )
    assert parent.id is not None
    for dataset_id in ids:
        service.add_dataset(parent.id, dataset_id, admin_user)

    pages = [
        _ids(
            service.get_member_datasets(
                parent.id, ANONYMOUS_USER, offset=offset, limit=2
            )
        )
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_child_collections_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_collections(session, admin_user)
    service = CollectionService(session)
    parent = service.create(
        CollectionCreate(name="parent", access_level=PUBLIC), user=admin_user
    )
    assert parent.id is not None
    for child_id in ids:
        service.add_child_collection(parent.id, child_id, admin_user)

    pages = [
        _ids(
            service.get_child_collections(
                parent.id, ANONYMOUS_USER, offset=offset, limit=2
            )
        )
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_devices_page_over_readable_rows(session: Session, admin_user):
    service = DeviceService(session)
    ids = []
    for i, level in enumerate(LEVELS):
        device = service.create(
            DeviceCreate(name=f"dev{i}", type="Tokamak", **_policy(level)),
            user=admin_user,
        )
        ids.append(device.id)

    pages = [
        _ids(service.get_multi(user=ANONYMOUS_USER, offset=offset, limit=2))
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_activity_inputs_page_over_readable_rows(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user)
    service = ActivityService(session)
    activity = service.create(
        ActivityCreate(activity_type=ActivityType.ANALYSIS), user=admin_user
    )
    activity_id = activity.id
    assert activity_id is not None
    for dataset_id in ids:
        service.add_input(
            activity_id=activity_id, dataset_id=dataset_id, user=admin_user
        )

    pages = [
        _ids(service.get_inputs(activity_id, ANONYMOUS_USER, offset=offset, limit=2))
        for offset in (0, 2, 4)
    ]

    public = _public(ids)
    assert pages == [public[:2], public[2:], []]


def test_inherited_policy_decides_visibility(session: Session, admin_user):
    _setup(session, admin_user)
    ShotService(session).create(
        ShotCreate(
            id="2",
            device_name="DEV",
            access_level=RESTRICTED,
            required_scopes=["dev_team"],
        ),
        user=admin_user,
    )
    service = DatasetService(session)
    open_ds = service.create(
        DatasetCreate(name="open", device_name="DEV", shot_id="1"), user=admin_user
    )
    closed_ds = service.create(
        DatasetCreate(name="closed", device_name="DEV", shot_id="2"), user=admin_user
    )

    anonymous = [d.id for d in service.get_datasets_for_device("DEV", ANONYMOUS_USER)]
    team = [d.id for d in service.get_datasets_for_device("DEV", TEAM)]

    assert anonymous == [open_ds.id]
    assert team == [open_ds.id, closed_ds.id]


def test_global_admin_reads_every_record(session: Session, admin_user):
    _setup(session, admin_user)
    ids = _make_datasets(session, admin_user)
    service = DatasetService(session)

    listed = [d.id for d in service.get_datasets_for_device("DEV", admin_user)]
    team_only = service.get(ids[2])
    assert team_only is not None
    service.check_read_access(team_only, admin_user)

    assert listed == ids
