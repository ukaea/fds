import pytest
from sqlmodel import Session

from fds.models.activity import ActivityCreate, ActivityType
from fds.models.collection import CollectionCreate
from fds.models.dataset import DatasetCreate, DatasetUpdate, GeneratedDatasetCreate
from fds.models.device import DeviceCreate
from fds.models.identity import ANONYMOUS_USER, AuthenticatedUser
from fds.models.policy import AccessLevel
from fds.models.shot import ShotCreate
from fds.models.source import SourceCreate, SourceKind, SourceUpdate
from fds.services.activity_service import ActivityService
from fds.services.collection_service import CollectionService
from fds.services.dataset_service import DatasetService
from fds.services.device_service import DeviceService
from fds.services.exceptions import ForbiddenError
from fds.services.shot_service import ShotService
from fds.services.source_service import SourceService

PUBLIC = AccessLevel.PUBLIC
RESTRICTED = AccessLevel.RESTRICTED
MAST_READER = AuthenticatedUser(id="reader", roles=("mast-read",))
MAST_WRITER = AuthenticatedUser(id="writer", roles=("mast-write",))
JET_READER = AuthenticatedUser(id="jet-reader", roles=("jet-read",))
JET_COLLAB = AuthenticatedUser(id="collab", roles=("jet-collab",))


@pytest.fixture
def mast(session: Session, admin_user: AuthenticatedUser) -> None:
    DeviceService(session).create(
        DeviceCreate(
            name="MAST",
            access_level=RESTRICTED,
            read_roles=["mast-read"],
            write_roles=["mast-write"],
        ),
        admin_user,
    )
    ShotService(session).create(ShotCreate(id="30421", device_name="MAST"), admin_user)


def restricted_dataset(
    session: Session, user: AuthenticatedUser, shot_id: str | None = "30421", **fields
):
    return DatasetService(session).create(
        DatasetCreate(
            name="thomson",
            device_name="MAST",
            shot_id=shot_id,
            access_level=RESTRICTED,
            **fields,
        ),
        user,
    )


@pytest.mark.usefixtures("mast")
@pytest.mark.parametrize("shot_id", ["30421", None], ids=["in-shot", "on-device"])
def test_device_read_roles_read_restricted_datasets(
    session: Session, admin_user: AuthenticatedUser, shot_id: str | None
):
    dataset = restricted_dataset(session, admin_user, shot_id)
    datasets = DatasetService(session)

    datasets.check_read_access(dataset, MAST_READER)
    with pytest.raises(ForbiddenError, match="one of roles: mast-read, mast-write"):
        datasets.check_read_access(dataset, JET_READER)


@pytest.mark.usefixtures("mast")
@pytest.mark.parametrize("shot_id", ["30421", None], ids=["in-shot", "on-device"])
def test_device_read_roles_read_restricted_collections(
    session: Session, admin_user: AuthenticatedUser, shot_id: str | None
):
    collections = CollectionService(session)
    collection = collections.create(
        CollectionCreate(
            name="analysed",
            device_name="MAST",
            shot_id=shot_id,
            access_level=RESTRICTED,
        ),
        admin_user,
    )

    collections.check_read_access(collection, MAST_READER)
    with pytest.raises(ForbiddenError, match="mast-read"):
        collections.check_read_access(collection, JET_READER)


@pytest.mark.usefixtures("mast")
def test_a_write_role_reads_too(session: Session, admin_user: AuthenticatedUser):
    dataset = restricted_dataset(session, admin_user)

    DatasetService(session).check_read_access(dataset, MAST_WRITER)


@pytest.mark.usefixtures("mast")
def test_any_one_listed_read_role_is_enough(
    session: Session, admin_user: AuthenticatedUser
):
    dataset = restricted_dataset(
        session, admin_user, read_roles=["mast-read", "jet-collab"]
    )

    DatasetService(session).check_read_access(dataset, JET_COLLAB)


def test_a_public_device_names_read_roles_for_its_restricted_records(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="MAST", access_level=PUBLIC, read_roles=["mast-read"]),
        admin_user,
    )
    dataset = DatasetService(session).create(
        DatasetCreate(name="thomson", device_name="MAST", access_level=RESTRICTED),
        admin_user,
    )

    DatasetService(session).check_read_access(dataset, MAST_READER)
    with pytest.raises(ForbiddenError, match="mast-read"):
        DatasetService(session).check_read_access(dataset, JET_READER)


def test_a_device_with_no_lists_is_fds_admin_only(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(DeviceCreate(name="JET"), admin_user)
    dataset = DatasetService(session).create(
        DatasetCreate(name="kk3", device_name="JET", access_level=RESTRICTED),
        admin_user,
    )

    with pytest.raises(ForbiddenError, match="requires role: fds-admin"):
        DatasetService(session).check_read_access(dataset, JET_READER)
    with pytest.raises(ForbiddenError, match="requires role: fds-admin"):
        DatasetService(session).create(
            DatasetCreate(name="lidar", device_name="JET"), JET_READER
        )


@pytest.mark.usefixtures("mast")
def test_a_read_role_cannot_write(session: Session):
    with pytest.raises(ForbiddenError, match="mast-write"):
        restricted_dataset(session, MAST_READER)
    with pytest.raises(ForbiddenError, match="mast-write"):
        ShotService(session).create(
            ShotCreate(id="30422", device_name="MAST"), MAST_READER
        )


@pytest.mark.usefixtures("mast")
def test_a_write_role_writes_shots_and_datasets(session: Session):
    ShotService(session).create(ShotCreate(id="30422", device_name="MAST"), MAST_WRITER)
    dataset = restricted_dataset(session, MAST_WRITER, shot_id="30422")
    assert dataset.id is not None
    datasets = DatasetService(session)

    datasets.update(id=dataset.id, obj_in=DatasetUpdate(level=2), user=MAST_WRITER)
    datasets.delete(dataset.id, MAST_WRITER)


@pytest.mark.usefixtures("mast")
def test_only_fds_admin_sets_write_roles(
    session: Session, admin_user: AuthenticatedUser
):
    with pytest.raises(ForbiddenError, match="fds-admin"):
        restricted_dataset(session, MAST_WRITER, write_roles=["jet-write"])

    dataset = restricted_dataset(session, admin_user)
    assert dataset.id is not None
    with pytest.raises(ForbiddenError, match="fds-admin"):
        DatasetService(session).update(
            id=dataset.id,
            obj_in=DatasetUpdate(write_roles=["jet-write"]),
            user=MAST_WRITER,
        )


@pytest.mark.usefixtures("mast")
def test_a_shots_write_roles_replace_its_devices(
    session: Session, admin_user: AuthenticatedUser
):
    ShotService(session).create(
        ShotCreate(id="30500", device_name="MAST", write_roles=["campaign-crew"]),
        admin_user,
    )
    crew = AuthenticatedUser(id="crew", roles=("campaign-crew",))

    restricted_dataset(session, crew, shot_id="30500")
    with pytest.raises(ForbiddenError, match="campaign-crew"):
        DatasetService(session).create(
            DatasetCreate(name="other", device_name="MAST", shot_id="30500"),
            MAST_WRITER,
        )


def test_an_embargoed_source_reads_as_public(
    session: Session, admin_user: AuthenticatedUser
):
    sources = SourceService(session)
    thomson = sources.create(
        SourceCreate(
            name="thomson",
            kind=SourceKind.INSTRUMENT,
            access_level=AccessLevel.EMBARGOED,
            read_roles=["thomson-team"],
        ),
        admin_user,
    )
    assert thomson.id is not None

    assert [s.name for s in sources.get_readable(ANONYMOUS_USER)] == ["thomson"]
    sources.get_readable_or_raise(thomson.id, ANONYMOUS_USER)


def test_a_restricted_source_is_hidden(session: Session, admin_user: AuthenticatedUser):
    sources = SourceService(session)
    thomson = sources.create(
        SourceCreate(
            name="thomson",
            kind=SourceKind.INSTRUMENT,
            access_level=RESTRICTED,
            read_roles=["thomson-team"],
        ),
        admin_user,
    )
    sources.create(
        SourceCreate(name="efit", kind=SourceKind.SOFTWARE, access_level=PUBLIC),
        admin_user,
    )
    assert thomson.id is not None
    team = AuthenticatedUser(id="team", roles=("thomson-team",))

    assert [s.name for s in sources.get_readable(ANONYMOUS_USER)] == ["efit"]
    assert [s.name for s in sources.get_readable(team)] == ["thomson", "efit"]
    with pytest.raises(ForbiddenError, match="thomson-team"):
        sources.get_readable_or_raise(thomson.id, JET_READER)


@pytest.mark.usefixtures("mast")
def test_a_source_uses_its_devices_lists(session: Session):
    sources = SourceService(session)
    thomson = sources.create(
        SourceCreate(name="thomson", kind=SourceKind.INSTRUMENT, device_name="MAST"),
        MAST_WRITER,
    )
    assert thomson.id is not None

    sources.get_readable_or_raise(thomson.id, MAST_READER)
    with pytest.raises(ForbiddenError, match="mast-read"):
        sources.get_readable_or_raise(thomson.id, JET_READER)
    sources.update(
        id=thomson.id, obj_in=SourceUpdate(description="Ruby laser"), user=MAST_WRITER
    )


def test_fds_admin_hands_over_a_source_on_no_device(
    session: Session, admin_user: AuthenticatedUser
):
    sources = SourceService(session)
    jintrac = sources.create(
        SourceCreate(
            name="jintrac",
            kind=SourceKind.SOFTWARE,
            access_level=PUBLIC,
            write_roles=["jintrac-dev"],
        ),
        admin_user,
    )
    assert jintrac.id is not None
    developer = AuthenticatedUser(id="dev", roles=("jintrac-dev",))

    sources.update(
        id=jintrac.id, obj_in=SourceUpdate(description="Suite"), user=developer
    )
    with pytest.raises(ForbiddenError, match="jintrac-dev"):
        sources.update(
            id=jintrac.id, obj_in=SourceUpdate(description="Mine"), user=MAST_WRITER
        )


@pytest.mark.usefixtures("mast")
def test_a_writer_creates_a_run_with_its_outputs(session: Session):
    activity = ActivityService(session).create(
        ActivityCreate(
            activity_type=ActivityType.SIMULATION,
            outputs=[
                GeneratedDatasetCreate(
                    name="jetto", device_name="MAST", shot_id="30421"
                )
            ],
        ),
        MAST_WRITER,
    )

    assert [d.name for d in activity.datasets] == ["jetto"]


@pytest.mark.usefixtures("mast")
def test_a_run_with_no_outputs_needs_fds_admin(session: Session):
    with pytest.raises(ForbiddenError, match="fds-admin"):
        ActivityService(session).create(
            ActivityCreate(activity_type=ActivityType.SIMULATION), MAST_WRITER
        )


@pytest.mark.usefixtures("mast")
def test_writing_a_run_needs_every_output(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="JET", write_roles=["jet-write"]), admin_user
    )
    activity = ActivityService(session).create(
        ActivityCreate(
            activity_type=ActivityType.SIMULATION,
            outputs=[
                GeneratedDatasetCreate(name="mast-run", device_name="MAST"),
                GeneratedDatasetCreate(name="jet-run", device_name="JET"),
            ],
        ),
        admin_user,
    )
    assert activity.id is not None

    with pytest.raises(ForbiddenError, match="jet-write"):
        ActivityService(session).delete(activity.id, MAST_WRITER)


@pytest.mark.usefixtures("mast")
def test_naming_an_unreadable_source_is_refused(
    session: Session, admin_user: AuthenticatedUser
):
    hidden = SourceService(session).create(
        SourceCreate(
            name="hidden-code",
            kind=SourceKind.SOFTWARE,
            access_level=RESTRICTED,
            read_roles=["code-team"],
        ),
        admin_user,
    )

    with pytest.raises(ForbiddenError, match="code-team"):
        ActivityService(session).create(
            ActivityCreate(
                activity_type=ActivityType.SIMULATION,
                source_id=hidden.id,
                outputs=[GeneratedDatasetCreate(name="run", device_name="MAST")],
            ),
            MAST_WRITER,
        )


@pytest.mark.usefixtures("mast")
def test_naming_an_unreadable_input_is_refused(
    session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="JET", access_level=RESTRICTED, read_roles=["jet-read"]),
        admin_user,
    )
    jet_data = DatasetService(session).create(
        DatasetCreate(name="jet-profiles", device_name="JET"), admin_user
    )
    assert jet_data.id is not None

    with pytest.raises(ForbiddenError, match="jet-read"):
        ActivityService(session).create(
            ActivityCreate(
                activity_type=ActivityType.SIMULATION,
                inputs=[jet_data.id],
                outputs=[GeneratedDatasetCreate(name="run", device_name="MAST")],
            ),
            MAST_WRITER,
        )


@pytest.mark.usefixtures("mast")
def test_a_run_leaves_out_sources_the_caller_may_not_read(
    session: Session, admin_user: AuthenticatedUser
):
    hidden = SourceService(session).create(
        SourceCreate(
            name="hidden-code",
            kind=SourceKind.SOFTWARE,
            access_level=RESTRICTED,
            read_roles=["code-team"],
        ),
        admin_user,
    )
    activities = ActivityService(session)
    activity = activities.create(
        ActivityCreate(
            activity_type=ActivityType.SIMULATION,
            source_id=hidden.id,
            outputs=[GeneratedDatasetCreate(name="run", device_name="MAST")],
        ),
        admin_user,
    )

    assert activities.to_read_model(activity, MAST_READER).source_id is None
    assert activities.to_read_model(activity, admin_user).source_id == hidden.id
    document = activities.to_dcat(activity, "https://fds.example", MAST_READER)
    assert "prov:wasAssociatedWith" not in document
