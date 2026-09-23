from app.auth.security import AuthenticatedUser
from app.models.activity import (
    ActivityAgentInput,
    ActivityCreate,
    ActivityDelegationInput,
    AgentRole,
)
from app.models.dataset import DatasetCreate
from app.models.policy import AccessLevel
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.jsonld import FUEL_ORCHESTRATOR_ROLE, map_dataset_to_dcat
from app.services.source_service import SourceService

admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
BASE = "http://testserver"


def _dataset_from_delegated_run(session):
    """A dataset produced by an analysis run whose executor ``code`` acted on
    behalf of the orchestrator ``scheduler``. Returns (dataset, code_id, sched_id).
    """
    code = SourceService(session).create(
        SourceCreate(name="analysis-code", kind=SourceKind.SOFTWARE), user=admin
    )
    scheduler = SourceService(session).create(
        SourceCreate(name="scheduler", kind=SourceKind.SOFTWARE), user=admin
    )
    assert code.id is not None and scheduler.id is not None

    activity = ActivityService(session).create(
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
        user=admin,
    )
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="derived",
            level=2,
            url="s3://bucket/derived",
            access_level=AccessLevel.PUBLIC,
            activity_id=activity.id,
        ),
        user=admin,
    )
    session.commit()
    return dataset, code.id, scheduler.id


def test_delegate_agent_serialises_acted_on_behalf_of(session):
    """The delegate (executor) node carries prov:actedOnBehalfOf to the responsible."""
    dataset, code_id, scheduler_id = _dataset_from_delegated_run(session)

    prov = map_dataset_to_dcat(dataset, BASE)["prov:wasGeneratedBy"]
    executor = prov["prov:wasAssociatedWith"]
    assert executor["@id"] == f"{BASE}/sources/{code_id}"
    assert executor["prov:actedOnBehalfOf"] == [
        {"@id": f"{BASE}/sources/{scheduler_id}"}
    ]


def test_non_delegate_agent_has_no_acted_on_behalf_of(session):
    """An orchestrator that is not a subordinate carries no prov:actedOnBehalfOf."""
    dataset, _code_id, _scheduler_id = _dataset_from_delegated_run(session)

    prov = map_dataset_to_dcat(dataset, BASE)["prov:wasGeneratedBy"]
    orchestrator = next(
        assoc["prov:agent"]
        for assoc in prov["prov:qualifiedAssociation"]
        if assoc["prov:hadRole"] == {"@id": FUEL_ORCHESTRATOR_ROLE}
    )
    assert "prov:actedOnBehalfOf" not in orchestrator
