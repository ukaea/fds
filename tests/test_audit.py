import pytest
from sqlmodel import Session

from app.core.context import request_context, set_actor
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import Device, DeviceCreate, DeviceUpdate
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def audit_lines(lines: list[dict], action: str | None = None) -> list[dict]:
    found = [line for line in lines if line.get("logger") == "fds.audit"]
    if action is not None:
        found = [line for line in found if line["event"] == action]
    return found


@pytest.fixture
def seeded(session: Session, admin_user: AuthenticatedUser):
    """A device and a shot to hang datasets and collections off."""
    device = DeviceService(session).create(DeviceCreate(name="mast"), admin_user)
    shot = ShotService(session).create(
        ShotCreate(id="30420", device_name="mast"), admin_user
    )
    return device, shot


class TestMutationsAreRecorded:
    def test_create_names_the_resource(self, session, admin_user, log_lines):
        DeviceService(session).create(DeviceCreate(name="mast"), admin_user)

        (line,) = audit_lines(log_lines(), "device.insert")
        assert line["resource_type"] == "device"
        assert line["operation"] == "insert"
        assert line["name"] == "mast"
        assert line["id"] == 1

    def test_delete_is_recorded(self, session, admin_user, log_lines):
        service = DeviceService(session)
        device = service.create(DeviceCreate(name="mast"), admin_user)
        log_lines()

        service.delete(device.name, admin_user)

        (line,) = audit_lines(log_lines(), "device.delete")
        assert line["name"] == "mast"

    def test_shot_and_dataset_creates_are_recorded(
        self, session, admin_user, seeded, log_lines
    ):
        DatasetService(session).create(
            DatasetCreate(name="ip", shot_id="30420", device_name="mast"), admin_user
        )

        actions = {line["event"] for line in audit_lines(log_lines())}
        assert "dataset.insert" in actions

    def test_link_table_write_is_named_for_its_operation(
        self, session, admin_user, seeded, log_lines
    ):
        """add_dataset writes a join row, not a Collection row."""
        dataset = DatasetService(session).create(
            DatasetCreate(name="ip", shot_id="30420", device_name="mast"), admin_user
        )
        collection = CollectionService(session).create(
            CollectionCreate(name="cal", shot_id="30420", device_name="mast"),
            admin_user,
        )
        log_lines()
        assert collection.id is not None and dataset.id is not None

        CollectionService(session).add_dataset(collection.id, dataset.id, admin_user)

        assert audit_lines(log_lines(), "collection.add_dataset")


class TestPolicyChanges:
    def test_before_and_after_are_both_recorded(self, session, admin_user, log_lines):
        """The gotcha: History.deleted is empty if the row was never loaded.

        Assigning to an expired instance records the new value and no old one,
        which produces a plausible-looking audit line that has quietly lost the
        thing it exists to record. The service path loads via get() first, so
        this passes; it fails silently if that ever changes.
        """
        service = DeviceService(session)
        device = service.create(
            DeviceCreate(name="mast", access_level=AccessLevel.EMBARGOED), admin_user
        )
        log_lines()

        service.update(
            device_name=device.name,
            obj_in=DeviceUpdate(access_level=AccessLevel.PUBLIC),
            user=admin_user,
        )

        (line,) = audit_lines(log_lines(), "device.update")
        assert line["access_level_before"] == "embargoed"
        assert line["access_level_after"] == "public"
        assert "access_level" in line["changed_fields"]

    def test_non_policy_fields_contribute_names_only(
        self, session, admin_user, log_lines
    ):
        """Free text must not reach the log, only the fact that it changed."""
        service = DeviceService(session)
        device = service.create(DeviceCreate(name="mast"), admin_user)
        log_lines()

        service.update(
            device_name=device.name,
            obj_in=DeviceUpdate(description="a very long description"),
            user=admin_user,
        )

        (line,) = audit_lines(log_lines(), "device.update")
        assert "description" in line["changed_fields"]
        assert "a very long description" not in str(line)


class TestTransactionBoundaries:
    def test_rollback_emits_nothing(self, session, log_lines):
        session.add(Device(name="never-committed"))
        session.flush()
        session.rollback()

        assert audit_lines(log_lines()) == []

    def test_write_outside_a_request_still_audits(self, session, admin_user, log_lines):
        """The demo script and any future CLI go through the same listener."""
        DeviceService(session).create(DeviceCreate(name="mast"), admin_user)

        (line,) = audit_lines(log_lines(), "device.insert")
        assert line["actor_id"] is None


class TestActor:
    def test_actor_is_named_when_there_is_a_request(
        self, session, admin_user, log_lines
    ):
        user = AuthenticatedUser(id="hashed-subject", scopes=("fds-admin",))
        with request_context():
            set_actor(user)
            DeviceService(session).create(DeviceCreate(name="mast"), admin_user)

            (line,) = audit_lines(log_lines(), "device.insert")
            assert line["actor_id"] == "hashed-subject"
