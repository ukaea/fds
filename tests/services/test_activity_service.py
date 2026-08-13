import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import (
    ActivityAgentInput,
    ActivityCreate,
    ActivityDelegationInput,
    ActivityType,
    ActivityUpdate,
    AgentRole,
)
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.shot import ShotCreate
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.exceptions import FDSValidationError, ResourceNotFoundError
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
    source1 = source_service.create(
        SourceCreate(name="Source 1", kind=SourceKind.SOFTWARE), user=admin_user
    )
    source2 = source_service.create(
        SourceCreate(name="Source 2", kind=SourceKind.SOFTWARE), user=admin_user
    )
    return shot, dataset, source1, source2


def test_create_activity(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=source1.id, activity_type=ActivityType.SIMULATION),
        user=admin_user,
    )
    assert activity is not None
    assert activity.id is not None
    assert activity.source_id == source1.id
    assert activity.activity_type == "simulation"


def test_create_activity_with_metadata(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, source1, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(
            source_id=source1.id,
            activity_type=ActivityType.SIMULATION,
            source_version="v1.2.3",
            parameters={"dt": 0.01, "nodes": 100},
        ),
        user=admin_user,
    )
    assert activity.source_version == "v1.2.3"
    assert activity.activity_type == "simulation"
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
        ActivityCreate(source_id=source1.id, activity_type=ActivityType.MEASUREMENT),
        user=admin_user,
    )
    assert activity.id is not None
    updated = activity_service.update(
        id=activity.id,
        obj_in=ActivityUpdate(
            activity_type=ActivityType.SIMULATION, source_version="v2.0"
        ),
        user=admin_user,
    )
    assert updated.activity_type == "simulation"
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
    admin_user: AuthenticatedUser,
):
    """A single Activity can be referenced by multiple Datasets."""
    device_service.create(
        DeviceCreate(name="shared-device", type="Test"), user=admin_user
    )
    shot = shot_service.create(
        ShotCreate(id="s1", device_name="shared-device"), user=admin_user
    )
    source = source_service.create(
        SourceCreate(name="pipeline", kind=SourceKind.SOFTWARE), user=admin_user
    )
    assert source.id is not None
    activity = activity_service.create(
        ActivityCreate(source_id=source.id, activity_type=ActivityType.MEASUREMENT),
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


def test_create_activity_with_inline_instrument(
    activity_service: ActivityService,
    source_service: SourceService,
    admin_user: AuthenticatedUser,
):
    instrument = source_service.create(
        SourceCreate(name="thomson", kind=SourceKind.INSTRUMENT), user=admin_user
    )
    assert instrument.id is not None

    activity = activity_service.create(
        ActivityCreate(
            activity_type=ActivityType.MEASUREMENT, instruments=[instrument.id]
        ),
        user=admin_user,
    )
    assert activity.id is not None
    assert [s.id for s in activity.instruments] == [instrument.id]


def test_create_activity_rejects_non_instrument_in_instruments(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, _, software = setup_data  # default kind=software
    assert software.id is not None

    with pytest.raises(FDSValidationError):
        activity_service.create(
            ActivityCreate(
                activity_type=ActivityType.MEASUREMENT, instruments=[software.id]
            ),
            user=admin_user,
        )


def test_create_activity_with_inline_agents(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, scheduler = setup_data  # both software
    assert scheduler.id is not None

    activity = activity_service.create(
        ActivityCreate(
            source_id=code.id,
            activity_type=ActivityType.ANALYSIS,
            agents=[
                ActivityAgentInput(source_id=scheduler.id, role=AgentRole.ORCHESTRATOR)
            ],
        ),
        user=admin_user,
    )
    assert activity.id is not None
    assert len(activity.agent_links) == 1
    assert activity.agent_links[0].source_id == scheduler.id
    assert activity.agent_links[0].role == "orchestrator"

    # The orchestrator is discoverable via get_for_source.
    found = activity_service.get_for_source(scheduler.id)
    assert activity.id in [a.id for a in found]


def test_create_activity_rejects_instrument_as_agent(
    activity_service: ActivityService,
    source_service: SourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, _ = setup_data
    instrument = source_service.create(
        SourceCreate(name="probe", kind=SourceKind.INSTRUMENT), user=admin_user
    )
    assert instrument.id is not None

    with pytest.raises(FDSValidationError):
        activity_service.create(
            ActivityCreate(
                source_id=code.id,
                agents=[
                    ActivityAgentInput(
                        source_id=instrument.id, role=AgentRole.ORCHESTRATOR
                    )
                ],
            ),
            user=admin_user,
        )


def test_add_remove_input(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, dataset, code, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None
    assert dataset.id is not None

    activity_service.add_input(
        activity_id=activity.id, dataset_id=dataset.id, user=admin_user
    )
    assert [d.id for d in activity_service.get_inputs(activity.id)] == [dataset.id]

    # Idempotent.
    activity_service.add_input(
        activity_id=activity.id, dataset_id=dataset.id, user=admin_user
    )
    assert len(activity_service.get_inputs(activity.id)) == 1

    activity_service.remove_input(
        activity_id=activity.id, dataset_id=dataset.id, user=admin_user
    )
    assert activity_service.get_inputs(activity.id) == []


def test_add_remove_instrument(
    activity_service: ActivityService,
    source_service: SourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, _ = setup_data
    instrument = source_service.create(
        SourceCreate(name="probe", kind=SourceKind.INSTRUMENT), user=admin_user
    )
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None
    assert instrument.id is not None

    activity_service.add_instrument(
        activity_id=activity.id, source_id=instrument.id, user=admin_user
    )
    assert [s.id for s in activity_service.get_instruments(activity.id)] == [
        instrument.id
    ]
    activity_service.remove_instrument(
        activity_id=activity.id, source_id=instrument.id, user=admin_user
    )
    assert activity_service.get_instruments(activity.id) == []


def test_add_remove_agent(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, scheduler = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None
    assert scheduler.id is not None

    activity_service.add_agent(
        activity_id=activity.id,
        source_id=scheduler.id,
        role=AgentRole.ORCHESTRATOR,
        user=admin_user,
    )
    agents = activity_service.get_agents(activity.id)
    assert [(a.source_id, a.role) for a in agents] == [
        (scheduler.id, AgentRole.ORCHESTRATOR)
    ]

    # Re-adding updates the role.
    activity_service.add_agent(
        activity_id=activity.id,
        source_id=scheduler.id,
        role=AgentRole.EXECUTOR,
        user=admin_user,
    )
    assert activity_service.get_agents(activity.id)[0].role == AgentRole.EXECUTOR

    activity_service.remove_agent(
        activity_id=activity.id, source_id=scheduler.id, user=admin_user
    )
    assert activity_service.get_agents(activity.id) == []


def test_create_activity_with_inline_delegation(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, scheduler = setup_data
    assert code.id is not None
    assert scheduler.id is not None

    activity = activity_service.create(
        ActivityCreate(
            source_id=code.id,
            activity_type=ActivityType.ANALYSIS,
            agents=[
                ActivityAgentInput(source_id=scheduler.id, role=AgentRole.ORCHESTRATOR)
            ],
            delegations=[
                ActivityDelegationInput(
                    subordinate_source_id=code.id,
                    responsible_source_id=scheduler.id,
                )
            ],
        ),
        user=admin_user,
    )
    assert activity.id is not None
    delegations = activity_service.get_delegations(activity.id)
    assert [
        (d.subordinate_source_id, d.responsible_source_id) for d in delegations
    ] == [(code.id, scheduler.id)]


def test_add_remove_delegation(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, scheduler = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None
    assert code.id is not None
    assert scheduler.id is not None

    activity_service.add_agent(
        activity_id=activity.id,
        source_id=scheduler.id,
        role=AgentRole.ORCHESTRATOR,
        user=admin_user,
    )
    activity_service.add_delegation(
        activity_id=activity.id,
        subordinate_source_id=code.id,
        responsible_source_id=scheduler.id,
        user=admin_user,
    )
    delegations = activity_service.get_delegations(activity.id)
    assert [
        (d.subordinate_source_id, d.responsible_source_id) for d in delegations
    ] == [(code.id, scheduler.id)]

    # Idempotent.
    activity_service.add_delegation(
        activity_id=activity.id,
        subordinate_source_id=code.id,
        responsible_source_id=scheduler.id,
        user=admin_user,
    )
    assert len(activity_service.get_delegations(activity.id)) == 1

    activity_service.remove_delegation(
        activity_id=activity.id,
        subordinate_source_id=code.id,
        responsible_source_id=scheduler.id,
        user=admin_user,
    )
    assert activity_service.get_delegations(activity.id) == []


def test_delegation_rejects_instrument(
    activity_service: ActivityService,
    source_service: SourceService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, _ = setup_data
    instrument = source_service.create(
        SourceCreate(name="probe", kind=SourceKind.INSTRUMENT), user=admin_user
    )
    assert code.id is not None
    assert instrument.id is not None

    with pytest.raises(FDSValidationError, match="is an instrument"):
        activity_service.create(
            ActivityCreate(
                source_id=code.id,
                agents=[
                    ActivityAgentInput(
                        source_id=instrument.id, role=AgentRole.ORCHESTRATOR
                    )
                ],
                delegations=[
                    ActivityDelegationInput(
                        subordinate_source_id=code.id,
                        responsible_source_id=instrument.id,
                    )
                ],
            ),
            user=admin_user,
        )


def test_add_agent_cannot_duplicate_the_executor(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, _ = setup_data
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None and code.id is not None
    with pytest.raises(FDSValidationError, match="already the executor"):
        activity_service.add_agent(
            activity_id=activity.id,
            source_id=code.id,
            role=AgentRole.ORCHESTRATOR,
            user=admin_user,
        )


def test_delegation_to_unassociated_agent_rejected(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
    source_service: SourceService,
):
    """A delegation whose ends are not agents of the run would be stored but
    never serialised, so it is refused at the boundary instead."""
    _, _, code, _ = setup_data
    stranger = source_service.create(
        SourceCreate(name="stranger", kind=SourceKind.SOFTWARE), user=admin_user
    )
    activity = activity_service.create(
        ActivityCreate(source_id=code.id), user=admin_user
    )
    assert activity.id is not None and code.id is not None and stranger.id is not None

    with pytest.raises(FDSValidationError, match="not an agent of this activity"):
        activity_service.add_delegation(
            activity_id=activity.id,
            subordinate_source_id=code.id,
            responsible_source_id=stranger.id,
            user=admin_user,
        )


def test_cannot_strip_an_agent_a_delegation_depends_on(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
):
    _, _, code, scheduler = setup_data
    activity = activity_service.create(
        ActivityCreate(
            source_id=code.id,
            agents=[
                ActivityAgentInput(source_id=scheduler.id, role=AgentRole.ORCHESTRATOR)
            ],
            delegations=[
                ActivityDelegationInput(
                    subordinate_source_id=code.id,
                    responsible_source_id=scheduler.id,
                )
            ],
        ),
        user=admin_user,
    )
    assert activity.id is not None and scheduler.id is not None

    with pytest.raises(FDSValidationError, match="takes part in a delegation"):
        activity_service.remove_agent(
            activity_id=activity.id, source_id=scheduler.id, user=admin_user
        )


def test_cannot_reassign_executor_a_delegation_depends_on(
    activity_service: ActivityService,
    setup_data,
    admin_user: AuthenticatedUser,
    source_service: SourceService,
):
    _, _, code, scheduler = setup_data
    other = source_service.create(
        SourceCreate(name="other-code", kind=SourceKind.SOFTWARE), user=admin_user
    )
    activity = activity_service.create(
        ActivityCreate(
            source_id=code.id,
            agents=[
                ActivityAgentInput(source_id=scheduler.id, role=AgentRole.ORCHESTRATOR)
            ],
            delegations=[
                ActivityDelegationInput(
                    subordinate_source_id=code.id,
                    responsible_source_id=scheduler.id,
                )
            ],
        ),
        user=admin_user,
    )
    assert activity.id is not None

    with pytest.raises(FDSValidationError, match="takes part in a delegation"):
        activity_service.update(
            id=activity.id,
            obj_in=ActivityUpdate(source_id=other.id),
            user=admin_user,
        )
