import pytest
from pydantic import ValidationError

from app.models.activity import (
    ActivityAgentInput,
    ActivityCreate,
    ActivityDelegationInput,
    AgentRole,
)
from app.models.dataset import DatasetDerivationCreate
from app.models.source import SourceCreate, SourceKind


class TestActivityAgents:
    def test_agent_may_not_duplicate_the_executor(self):
        """Otherwise the graph carries two prov:Association nodes for one agent,
        each claiming a different role."""
        with pytest.raises(ValidationError, match="already the executor"):
            ActivityCreate(
                source_id=1,
                agents=[ActivityAgentInput(source_id=1, role=AgentRole.ORCHESTRATOR)],
            )

    def test_agent_may_not_be_listed_twice(self):
        with pytest.raises(ValidationError, match="listed as an agent twice"):
            ActivityCreate(
                source_id=1,
                agents=[
                    ActivityAgentInput(source_id=2, role=AgentRole.ORCHESTRATOR),
                    ActivityAgentInput(source_id=2, role=AgentRole.EXECUTOR),
                ],
            )

    def test_distinct_agents_are_accepted(self):
        activity = ActivityCreate(
            source_id=1,
            agents=[
                ActivityAgentInput(source_id=2, role=AgentRole.ORCHESTRATOR),
                ActivityAgentInput(source_id=3, role=AgentRole.EXECUTOR),
            ],
        )
        assert len(activity.agents) == 2

    def test_agent_without_an_executor_is_accepted(self):
        """source_id is optional, so an agent cannot collide with a missing one."""
        activity = ActivityCreate(
            agents=[ActivityAgentInput(source_id=2, role=AgentRole.ORCHESTRATOR)]
        )
        assert activity.source_id is None


class TestActivityDelegations:
    def test_a_source_may_not_act_on_behalf_of_itself(self):
        with pytest.raises(ValidationError, match="act on behalf of itself"):
            ActivityDelegationInput(subordinate_source_id=1, responsible_source_id=1)

    def test_delegation_ends_must_be_agents_of_the_activity(self):
        """A delegation naming an unassociated agent would be stored but never
        serialised, since actedOnBehalfOf hangs off the association list."""
        with pytest.raises(ValidationError, match="not an agent of this activity"):
            ActivityCreate(
                source_id=1,
                delegations=[
                    ActivityDelegationInput(
                        subordinate_source_id=1, responsible_source_id=9
                    )
                ],
            )

    def test_delegation_between_the_executor_and_an_agent_is_accepted(self):
        activity = ActivityCreate(
            source_id=1,
            agents=[ActivityAgentInput(source_id=2, role=AgentRole.ORCHESTRATOR)],
            delegations=[
                ActivityDelegationInput(
                    subordinate_source_id=1, responsible_source_id=2
                )
            ],
        )
        assert len(activity.delegations) == 1


class TestDatasetDerivation:
    def test_must_identify_its_upstream(self):
        with pytest.raises(ValidationError, match="must identify its upstream"):
            DatasetDerivationCreate()

    def test_may_not_claim_two_identities(self):
        with pytest.raises(ValidationError, match="not both"):
            DatasetDerivationCreate(source_dataset_id=1, source_identifier="10.1/x")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"source_dataset_id": 1},
            {"source_identifier": "10.5281/zenodo.1"},
            {"source_label": "Legacy tape"},
            {"source_description": "recovered from a 1998 archive"},
            {"source_identifier": "10.5281/zenodo.1", "source_label": "Zen"},
        ],
    )
    def test_any_single_form_of_identification_is_enough(self, kwargs: dict):
        assert DatasetDerivationCreate(**kwargs)


class TestSourceKind:
    def test_kind_is_required(self):
        """The kinds straddle two PROV classes, so an unclassified source cannot be
        placed in the graph at all without guessing which side it falls on."""
        with pytest.raises(ValidationError):
            SourceCreate(name="unclassified")  # type: ignore[missing-argument]

    @pytest.mark.parametrize("kind", list(SourceKind))
    def test_every_kind_is_accepted(self, kind: SourceKind):
        assert SourceCreate(name="s", kind=kind).kind is kind
