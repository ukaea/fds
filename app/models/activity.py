from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Self

from pydantic import model_validator
from sqlmodel import JSON, Column, Field, Relationship, SQLModel


class ActivityType(str, Enum):
    """
    Controlled vocabulary for the type of activity that produced a dataset.

    Maps to ``prov:type`` in PROV-O JSON-LD.
    """

    MEASUREMENT = "measurement"
    SIMULATION = "simulation"
    ANALYSIS = "analysis"
    CALIBRATION = "calibration"


class AgentRole(str, Enum):
    """The function an agent served in an Activity, serialised as the
    ``prov:hadRole`` of its ``prov:Association``.
    """

    EXECUTOR = "executor"
    ORCHESTRATOR = "orchestrator"


if TYPE_CHECKING:
    from .collection import Collection
    from .dataset import Dataset
    from .source import Source


class ActivityInput(SQLModel, table=True):
    """Datasets that an Activity consumed as inputs."""

    activity_id: int = Field(foreign_key="activity.id", primary_key=True)
    dataset_id: int = Field(foreign_key="dataset.id", primary_key=True)


class ActivityInstrument(SQLModel, table=True):
    """Instruments that an Activity used — Sources of kind ``instrument``."""

    activity_id: int = Field(foreign_key="activity.id", primary_key=True)
    source_id: int = Field(foreign_key="source.id", primary_key=True)


class ActivityAgent(SQLModel, table=True):
    """Additional agents associated with an Activity, beyond its executor."""

    activity_id: int = Field(foreign_key="activity.id", primary_key=True)
    source_id: int = Field(foreign_key="source.id", primary_key=True)
    role: AgentRole = Field(default=AgentRole.EXECUTOR)

    source: "Source" = Relationship()


class ActivityDelegation(SQLModel, table=True):
    """Delegation of responsibility within an Activity — ``prov:actedOnBehalfOf``.

    The ``subordinate`` agent acted under the ``responsible`` agent's authority
    for this run (e.g. an analysis code coordinated by a scheduler). Both ends are
    agents, never instruments; the edge is responsibility, not data flow, so it
    never enters the lineage plane. Activity-scoped — the same two agents may
    stand in different relationships in different runs.
    """

    activity_id: int = Field(foreign_key="activity.id", primary_key=True)
    subordinate_source_id: int = Field(foreign_key="source.id", primary_key=True)
    responsible_source_id: int = Field(foreign_key="source.id", primary_key=True)


class ActivityBase(SQLModel):
    source_id: int | None = Field(default=None, foreign_key="source.id")
    source_version: str | None = None
    activity_type: ActivityType | None = None
    parameters: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Activity(ActivityBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    source: "Source" = Relationship(back_populates="activities")
    datasets: list["Dataset"] = Relationship(back_populates="activity")
    collections: list["Collection"] = Relationship(back_populates="activity")
    input_datasets: list["Dataset"] = Relationship(link_model=ActivityInput)
    instruments: list["Source"] = Relationship(link_model=ActivityInstrument)
    agent_links: list["ActivityAgent"] = Relationship()
    delegation_links: list["ActivityDelegation"] = Relationship()


class ActivityAgentInput(SQLModel):
    """An additional agent (with role) to associate when creating an Activity."""

    source_id: int
    role: AgentRole


class ActivityDelegationInput(SQLModel):
    """A delegation to record when creating an Activity: the ``subordinate`` agent
    acted on behalf of the ``responsible`` agent. Both are agent Sources."""

    subordinate_source_id: int
    responsible_source_id: int

    @model_validator(mode="after")
    def ends_must_differ(self) -> Self:
        if self.subordinate_source_id == self.responsible_source_id:
            raise ValueError(
                f"a source cannot act on behalf of itself "
                f"(source {self.subordinate_source_id})"
            )
        return self


class ActivityCreate(ActivityBase):
    """Create an Activity and declare its whole provenance in one request.

    ``inputs`` are dataset ids the run consumed; ``instruments`` are instrument
    Source ids it used; ``agents`` are additional agents (beyond the primary
    ``source_id`` executor) with their roles; ``delegations`` record which agent
    acted on behalf of which (``prov:actedOnBehalfOf``). The service builds the
    join rows.
    """

    inputs: list[int] = Field(default_factory=list)
    instruments: list[int] = Field(default_factory=list)
    agents: list[ActivityAgentInput] = Field(default_factory=list)
    delegations: list[ActivityDelegationInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def agents_hold_one_role_each(self) -> Self:
        """An agent appears once, and never duplicates the executor.

        Either would emit two ``prov:Association`` nodes for one agent, each
        claiming a different role.
        """
        seen: set[int] = set()
        for agent in self.agents:
            if agent.source_id == self.source_id:
                raise ValueError(
                    f"source {agent.source_id} is already the executor of this "
                    "activity; an agent holds one role per activity"
                )
            if agent.source_id in seen:
                raise ValueError(
                    f"source {agent.source_id} is listed as an agent twice; "
                    "an agent holds one role per activity"
                )
            seen.add(agent.source_id)
        return self

    @model_validator(mode="after")
    def delegation_ends_are_agents(self) -> Self:
        """Both ends of a delegation are agents this request associates.

        A delegation between agents the activity never names would be stored but
        never serialised, since ``actedOnBehalfOf`` hangs off the association list.
        """
        associated = {agent.source_id for agent in self.agents}
        if self.source_id is not None:
            associated.add(self.source_id)
        for delegation in self.delegations:
            for source_id in (
                delegation.subordinate_source_id,
                delegation.responsible_source_id,
            ):
                if source_id not in associated:
                    raise ValueError(
                        f"source {source_id} is not an agent of this activity; "
                        "associate it before recording a delegation, or the edge "
                        "would not appear in the provenance graph"
                    )
        return self


class ActivityRead(ActivityBase):
    id: int


class ActivityInputRead(SQLModel):
    """An input-dataset link on an Activity (``prov:used``, role ``input``)."""

    activity_id: int
    dataset_id: int


class ActivityInstrumentRead(SQLModel):
    """An instrument link on an Activity (``prov:used``, role ``instrument``)."""

    activity_id: int
    source_id: int


class ActivityAgentRead(SQLModel):
    """An agent association (with role) on an Activity."""

    activity_id: int
    source_id: int
    role: AgentRole


class ActivityDelegationRead(SQLModel):
    """A delegation association on an Activity — ``prov:actedOnBehalfOf``."""

    activity_id: int
    subordinate_source_id: int
    responsible_source_id: int


class ActivityUpdate(SQLModel):
    source_id: int | None = None
    source_version: str | None = None
    activity_type: ActivityType | None = None
    parameters: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime | None = None
    ended_at: datetime | None = None
