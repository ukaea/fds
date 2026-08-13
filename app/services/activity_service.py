from collections.abc import Sequence

from sqlmodel import Session, col, or_, select

from app.auth.permissions import check_is_admin
from app.models.activity import (
    Activity,
    ActivityAgent,
    ActivityCreate,
    ActivityDelegation,
    ActivityInput,
    ActivityInstrument,
    ActivityUpdate,
    AgentRole,
)
from app.models.dataset import Dataset
from app.models.identity import AuthenticatedUser
from app.models.source import Source, SourceKind
from app.services.base_service import BaseService
from app.services.exceptions import FDSValidationError, ResourceNotFoundError
from app.services.source_service import SourceService


class ActivityService(BaseService[Activity, ActivityCreate, ActivityUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Activity, session=session)

    def create(self, obj_in: ActivityCreate, user: AuthenticatedUser) -> Activity:
        """Create an Activity and the provenance it declares.

        A single request registers the run plus its used inputs, the
        instruments it used, any additional agents (beyond the primary
        ``source_id`` executor), and any delegations between agents
        (``prov:actedOnBehalfOf``). Each of these can also be added or removed
        afterwards via the sub-resource methods.
        """
        check_is_admin(user)

        # Validate every reference up front so a bad id leaves nothing behind.
        if obj_in.source_id is not None and not SourceService(self.session).get(
            obj_in.source_id
        ):
            raise ResourceNotFoundError(f"Source {obj_in.source_id} not found")
        for dataset_id in obj_in.inputs:
            self._require_dataset(dataset_id)
        for source_id in obj_in.instruments:
            self._require_instrument(source_id)
        for agent in obj_in.agents:
            self._require_agent(agent.source_id)
        for delegation in obj_in.delegations:
            self._require_agent(delegation.subordinate_source_id)
            self._require_agent(delegation.responsible_source_id)

        activity = Activity.model_validate(
            obj_in.model_dump(
                exclude={"inputs", "instruments", "agents", "delegations"}
            )
        )
        self.session.add(activity)
        self.session.commit()
        self.session.refresh(activity)
        assert activity.id is not None

        for dataset_id in obj_in.inputs:
            self.session.add(
                ActivityInput(activity_id=activity.id, dataset_id=dataset_id)
            )
        for source_id in obj_in.instruments:
            self.session.add(
                ActivityInstrument(activity_id=activity.id, source_id=source_id)
            )
        for agent in obj_in.agents:
            self.session.add(
                ActivityAgent(
                    activity_id=activity.id,
                    source_id=agent.source_id,
                    role=agent.role,
                )
            )
        for delegation in obj_in.delegations:
            self.session.add(
                ActivityDelegation(
                    activity_id=activity.id,
                    subordinate_source_id=delegation.subordinate_source_id,
                    responsible_source_id=delegation.responsible_source_id,
                )
            )
        self.session.commit()
        self.session.refresh(activity)
        return activity

    def _require_activity(self, activity_id: int) -> Activity:
        activity = self.get(activity_id)
        if not activity:
            raise ResourceNotFoundError(f"Activity {activity_id} not found")
        return activity

    def _require_dataset(self, dataset_id: int) -> Dataset:
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        return dataset

    def _require_instrument(self, source_id: int) -> Source:
        source = self.session.get(Source, source_id)
        if not source:
            raise ResourceNotFoundError(f"Source {source_id} not found")
        if source.kind != SourceKind.INSTRUMENT:
            raise FDSValidationError(
                f"Source {source_id} is kind '{source.kind.value}', not 'instrument'"
            )
        return source

    def _require_agent(self, source_id: int) -> Source:
        source = self.session.get(Source, source_id)
        if not source:
            raise ResourceNotFoundError(f"Source {source_id} not found")
        if source.kind == SourceKind.INSTRUMENT:
            raise FDSValidationError(
                f"Source {source_id} is an instrument, which is an entity, not an agent"
            )
        return source

    def _require_distinct_from_executor(
        self, source_id: int, executor_source_id: int | None
    ) -> None:
        """An additional agent may not be the executor.

        The executor is ``Activity.source_id``; adding the same source again as a
        roled agent would emit two ``prov:Association`` nodes for one agent, each
        claiming a different role.
        """
        if executor_source_id is not None and source_id == executor_source_id:
            raise FDSValidationError(
                f"Source {source_id} is already the executor of this activity; "
                "an agent holds one role per activity"
            )

    def _require_no_delegation_depends_on(
        self, activity_id: int, source_id: int
    ) -> None:
        """Refuse to strip an agent that a delegation on this activity still names."""
        statement = select(ActivityDelegation).where(
            ActivityDelegation.activity_id == activity_id,
            or_(
                ActivityDelegation.subordinate_source_id == source_id,
                ActivityDelegation.responsible_source_id == source_id,
            ),
        )
        if self.session.exec(statement).first():
            raise FDSValidationError(
                f"Source {source_id} takes part in a delegation on this activity; "
                "remove the delegation first"
            )

    def _associated_source_ids(self, activity: Activity) -> set[int]:
        """The agents associated with an activity: its executor plus roled agents."""
        associated = {
            link.source_id for link in getattr(activity, "agent_links", None) or []
        }
        if activity.source_id is not None:
            associated.add(activity.source_id)
        return associated

    def _require_delegatable(
        self,
        subordinate_source_id: int,
        responsible_source_id: int,
        associated_source_ids: set[int],
    ) -> None:
        """Validate a delegation pair against persisted state.

        The create path gets the same guarantees from ``ActivityCreate``, which can
        see the whole request at once. This is the sub-resource equivalent, where
        the agents are already stored and the ids arrive as path parameters with no
        request body to validate.
        """
        if subordinate_source_id == responsible_source_id:
            raise FDSValidationError(
                f"A source cannot act on behalf of itself (source {subordinate_source_id})"
            )
        self._require_agent(subordinate_source_id)
        self._require_agent(responsible_source_id)
        for source_id in (subordinate_source_id, responsible_source_id):
            if source_id not in associated_source_ids:
                raise FDSValidationError(
                    f"Source {source_id} is not an agent of this activity; "
                    "associate it before recording a delegation, or the edge "
                    "would not appear in the provenance graph"
                )

    def update(
        self, *, id: int, obj_in: ActivityUpdate, user: AuthenticatedUser
    ) -> Activity:
        """Update an Activity. Requires global admin.

        Reassigning ``source_id`` would drop the previous executor from the
        association list, so it is refused while a delegation still names it.
        """
        check_is_admin(user)
        db_obj = self._require_activity(id)
        if (
            obj_in.source_id is not None
            and db_obj.source_id is not None
            and obj_in.source_id != db_obj.source_id
        ):
            assert db_obj.id is not None
            self._require_no_delegation_depends_on(db_obj.id, db_obj.source_id)
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """Delete an Activity. Requires global admin."""
        check_is_admin(user)
        self._require_activity(id)
        return self.delete_unchecked(id)

    def get_for_dataset(self, dataset_id: int) -> Activity:
        """Retrieve the Activity that produced the given Dataset."""
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        if not dataset.activity_id:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} has no associated activity"
            )
        return self._require_activity(dataset.activity_id)

    def add_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> ActivityInput:
        """Add an input dataset the Activity used. Idempotent. Requires admin."""
        check_is_admin(user)
        self._require_activity(activity_id)
        self._require_dataset(dataset_id)

        existing = self.session.get(ActivityInput, (activity_id, dataset_id))
        if existing:
            return existing
        link = ActivityInput(activity_id=activity_id, dataset_id=dataset_id)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an input dataset from an Activity. Requires admin."""
        check_is_admin(user)
        link = self.session.get(ActivityInput, (activity_id, dataset_id))
        if not link:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} is not an input of Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_inputs(
        self, activity_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Dataset]:
        """List the datasets an Activity used as inputs."""
        self._require_activity(activity_id)
        statement = (
            select(Dataset)
            .join(ActivityInput, col(ActivityInput.dataset_id) == col(Dataset.id))
            .where(ActivityInput.activity_id == activity_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def add_instrument(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> ActivityInstrument:
        """Add an instrument (a kind=instrument Source) the Activity used.

        Idempotent. Requires global admin.
        """
        check_is_admin(user)
        self._require_activity(activity_id)
        self._require_instrument(source_id)

        existing = self.session.get(ActivityInstrument, (activity_id, source_id))
        if existing:
            return existing
        link = ActivityInstrument(activity_id=activity_id, source_id=source_id)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_instrument(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an instrument from an Activity. Requires global admin."""
        check_is_admin(user)
        link = self.session.get(ActivityInstrument, (activity_id, source_id))
        if not link:
            raise ResourceNotFoundError(
                f"Source {source_id} is not an instrument of Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_instruments(
        self, activity_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Source]:
        """List the instruments an Activity used."""
        self._require_activity(activity_id)
        statement = (
            select(Source)
            .join(
                ActivityInstrument, col(ActivityInstrument.source_id) == col(Source.id)
            )
            .where(ActivityInstrument.activity_id == activity_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def add_agent(
        self,
        *,
        activity_id: int,
        source_id: int,
        role: AgentRole,
        user: AuthenticatedUser,
    ) -> ActivityAgent:
        """Associate an additional agent (with a role) with an Activity.

        Updates the role if the agent is already associated. The Source must not
        be an instrument. Requires global admin.
        """
        check_is_admin(user)
        activity = self._require_activity(activity_id)
        self._require_agent(source_id)
        self._require_distinct_from_executor(source_id, activity.source_id)

        existing = self.session.get(ActivityAgent, (activity_id, source_id))
        if existing:
            existing.role = role
            self.session.add(existing)
            self.session.commit()
            return existing
        link = ActivityAgent(activity_id=activity_id, source_id=source_id, role=role)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_agent(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an additional agent from an Activity. Requires global admin.

        Refused while a delegation on this activity still names the agent, which
        would leave that edge stranded and unserialisable.
        """
        check_is_admin(user)
        link = self.session.get(ActivityAgent, (activity_id, source_id))
        if not link:
            raise ResourceNotFoundError(
                f"Source {source_id} is not an agent of Activity {activity_id}"
            )
        self._require_no_delegation_depends_on(activity_id, source_id)
        self.session.delete(link)
        self.session.commit()
        return True

    def get_agents(
        self, activity_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[ActivityAgent]:
        """List the additional agent associations (with roles) for an Activity."""
        self._require_activity(activity_id)
        statement = (
            select(ActivityAgent)
            .where(ActivityAgent.activity_id == activity_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def add_delegation(
        self,
        *,
        activity_id: int,
        subordinate_source_id: int,
        responsible_source_id: int,
        user: AuthenticatedUser,
    ) -> ActivityDelegation:
        """Record that one agent acted on behalf of another for this Activity
        (``prov:actedOnBehalfOf``). Both must be agents (not instruments) and must
        differ. Idempotent. Requires global admin.
        """
        check_is_admin(user)
        activity = self._require_activity(activity_id)
        self._require_delegatable(
            subordinate_source_id,
            responsible_source_id,
            self._associated_source_ids(activity),
        )

        key = (activity_id, subordinate_source_id, responsible_source_id)
        existing = self.session.get(ActivityDelegation, key)
        if existing:
            return existing
        link = ActivityDelegation(
            activity_id=activity_id,
            subordinate_source_id=subordinate_source_id,
            responsible_source_id=responsible_source_id,
        )
        self.session.add(link)
        self.session.commit()
        return link

    def remove_delegation(
        self,
        *,
        activity_id: int,
        subordinate_source_id: int,
        responsible_source_id: int,
        user: AuthenticatedUser,
    ) -> bool:
        """Remove a delegation edge from an Activity. Requires global admin."""
        check_is_admin(user)
        key = (activity_id, subordinate_source_id, responsible_source_id)
        link = self.session.get(ActivityDelegation, key)
        if not link:
            raise ResourceNotFoundError(
                f"Source {subordinate_source_id} does not act on behalf of "
                f"source {responsible_source_id} in Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_delegations(
        self, activity_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[ActivityDelegation]:
        """List the delegation edges (``actedOnBehalfOf``) for an Activity."""
        self._require_activity(activity_id)
        statement = (
            select(ActivityDelegation)
            .where(ActivityDelegation.activity_id == activity_id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()

    def get_for_source(
        self, source_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Activity]:
        """Retrieve all Activities associated with a Source — as the primary
        executor (``source_id``) or as an additional agent (``ActivityAgent``).
        """
        agent_activity_ids = select(ActivityAgent.activity_id).where(
            ActivityAgent.source_id == source_id
        )
        statement = (
            select(Activity)
            .where(
                or_(
                    Activity.source_id == source_id,
                    col(Activity.id).in_(agent_activity_ids),
                )
            )
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
