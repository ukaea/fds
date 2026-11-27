from collections.abc import Sequence

from sqlmodel import Session, col, or_, select

from fds.auth.access_control import check_activity_write, check_read
from fds.auth.permissions import check_is_admin
from fds.core.context import ReadTier, record_restricted_access
from fds.models.activity import (
    Activity,
    ActivityAgent,
    ActivityCreate,
    ActivityDelegation,
    ActivityInput,
    ActivityInstrument,
    ActivityRead,
    ActivityUpdate,
    AgentRole,
)
from fds.models.collection import Collection
from fds.models.dataset import Dataset, DatasetCreate
from fds.models.identity import AuthenticatedUser
from fds.models.policy import AccessLevel
from fds.models.source import Source, SourceKind
from fds.services.base_service import BaseService
from fds.services.dataset_service import DatasetService
from fds.services.exceptions import FDSValidationError, ResourceNotFoundError
from fds.services.jsonld import map_activity_to_dcat
from fds.services.source_service import (
    readable_activity_sources,
    readable_source_ids,
)
from fds.services.visibility import read_page, readable_access_levels, readable_only


class ActivityService(BaseService[Activity, ActivityCreate, ActivityUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Activity, session=session)

    def create(self, obj_in: ActivityCreate, user: AuthenticatedUser) -> Activity:
        """Create an Activity, the provenance it declares and the Datasets it generated.

        A single request registers the Activity plus its used inputs, the
        instruments it used, any additional agents (beyond the primary
        ``source_id`` executor), any delegations between agents
        (``prov:actedOnBehalfOf``), and its outputs: the Datasets it generated,
        each created with this Activity as its ``activity_id``. All of it is
        committed together, so if any part is refused nothing is saved. The links
        can also be added or removed afterwards via the sub-resource methods.
        """
        # The outputs are checked as they are added: creating each needs write
        # access to its device or shot.
        if not obj_in.outputs:
            check_is_admin(user)

        # Validate every reference up front so a bad id leaves nothing behind.
        if obj_in.source_id is not None:
            self._require_source(obj_in.source_id, user)
        for dataset_id in obj_in.inputs:
            self._require_dataset(dataset_id, user)
        for source_id in obj_in.instruments:
            self._require_instrument(source_id, user)
        for agent in obj_in.agents:
            self._require_agent(agent.source_id, user)
        for delegation in obj_in.delegations:
            self._require_agent(delegation.subordinate_source, user)
            self._require_agent(delegation.responsible_source, user)

        activity = Activity.model_validate(
            obj_in.model_dump(
                exclude={"inputs", "instruments", "agents", "delegations", "outputs"}
            )
        )
        try:
            self.session.add(activity)
            self.session.flush()
            assert activity.id is not None

            for dataset_id in obj_in.inputs:
                self.session.add(
                    ActivityInput(activity=activity.id, dataset=dataset_id)
                )
            for source_id in obj_in.instruments:
                self.session.add(
                    ActivityInstrument(activity=activity.id, source=source_id)
                )
            for agent in obj_in.agents:
                self.session.add(
                    ActivityAgent(
                        activity=activity.id,
                        source_id=agent.source_id,
                        role=agent.role,
                    )
                )
            for delegation in obj_in.delegations:
                self.session.add(
                    ActivityDelegation(
                        activity=activity.id,
                        subordinate_source=delegation.subordinate_source,
                        responsible_source=delegation.responsible_source,
                    )
                )
            self.session.flush()

            datasets = DatasetService(self.session)
            for output in obj_in.outputs:
                datasets.add(
                    DatasetCreate(**output.model_dump(), activity_id=activity.id),
                    user,
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(activity)
        return activity

    def output_ids(self, activity: Activity, user: AuthenticatedUser) -> list[int]:
        """The ids of the Datasets ``activity`` generated that ``user`` may read, in
        the order they were created.

        Ids rise in creation order, so the outputs of a create come back in the
        order its request listed them.
        """
        outputs = readable_only(self.session, activity.datasets, user)
        return sorted(dataset.id for dataset in outputs if dataset.id is not None)

    def _require_activity(self, activity_id: int) -> Activity:
        activity = self.get(activity_id)
        if not activity:
            raise ResourceNotFoundError(f"Activity {activity_id} not found")
        return activity

    def get_readable_or_raise(
        self, activity_id: int, user: AuthenticatedUser
    ) -> Activity:
        """Retrieve an Activity by id, for a caller who may read it.

        An Activity has no access policy of its own. A caller may read it if
        they may read a dataset it generated or a collection that bundles it, and
        only fds-admin may read an Activity with neither. A read that only
        restricted records allow is recorded in the audit trail as a restricted
        read of the Activity.
        """
        activity = self._require_activity(activity_id)
        levels = readable_access_levels(
            self.session,
            Dataset,
            user,
            select(Dataset).where(Dataset.activity_id == activity_id),
        ) | readable_access_levels(
            self.session,
            Collection,
            user,
            select(Collection).where(Collection.activity_id == activity_id),
        )
        if not levels:
            check_is_admin(user)
        if levels <= {AccessLevel.RESTRICTED}:
            record_restricted_access("activity", activity_id, ReadTier.READ)
        return activity

    def to_dcat(
        self, activity: Activity, base_url: str, user: AuthenticatedUser
    ) -> dict:
        """The Activity's ``prov:Activity`` document, listing only the inputs and
        Sources ``user`` may read."""
        return map_activity_to_dcat(
            activity,
            base_url,
            inputs=readable_only(self.session, activity.input_datasets, user),
            sources=readable_activity_sources(self.session, [activity], user),
        )

    def to_read_model(
        self, activity: Activity, user: AuthenticatedUser
    ) -> ActivityRead:
        """The Activity as ``user`` may see it: its executor is left out unless
        ``user`` may read that Source."""
        read = ActivityRead.model_validate(activity)
        if read.source_id is not None and not readable_source_ids(
            self.session, {read.source_id}, user
        ):
            read.source_id = None
        return read

    # Naming a Dataset or Source in an Activity needs read access to it.

    def _require_dataset(self, dataset_id: int, user: AuthenticatedUser) -> Dataset:
        dataset = self.session.get(Dataset, dataset_id)
        if not dataset:
            raise ResourceNotFoundError(f"Dataset {dataset_id} not found")
        check_read(dataset, self.session, user)
        return dataset

    def _require_source(self, source_id: int, user: AuthenticatedUser) -> Source:
        source = self.session.get(Source, source_id)
        if not source:
            raise ResourceNotFoundError(f"Source {source_id} not found")
        check_read(source, self.session, user)
        return source

    def _require_instrument(self, source_id: int, user: AuthenticatedUser) -> Source:
        source = self._require_source(source_id, user)
        if source.kind != SourceKind.INSTRUMENT:
            raise FDSValidationError(
                f"Source {source_id} is kind '{source.kind.value}', not 'instrument'"
            )
        return source

    def _require_agent(self, source_id: int, user: AuthenticatedUser) -> Source:
        source = self._require_source(source_id, user)
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
            ActivityDelegation.activity == activity_id,
            or_(
                ActivityDelegation.subordinate_source == source_id,
                ActivityDelegation.responsible_source == source_id,
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
        user: AuthenticatedUser,
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
        self._require_agent(subordinate_source_id, user)
        self._require_agent(responsible_source_id, user)
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
        """Update an Activity. Requires write access to its outputs and bundles.

        Reassigning ``source_id`` would drop the previous executor from the
        association list, so it is refused while a delegation still names it.
        """
        check_activity_write(self.session, user, id)
        db_obj = self._require_activity(id)
        if obj_in.source_id is not None:
            self._require_source(obj_in.source_id, user)
        if (
            obj_in.source_id is not None
            and db_obj.source_id is not None
            and obj_in.source_id != db_obj.source_id
        ):
            assert db_obj.id is not None
            self._require_no_delegation_depends_on(db_obj.id, db_obj.source_id)
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """Delete an Activity. Requires write access to its outputs and bundles."""
        check_activity_write(self.session, user, id)
        self._require_activity(id)
        return self.delete_unchecked(id)

    def add_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> ActivityInput:
        """Add an input dataset the Activity used. Idempotent. Requires write
        access to the Activity and read access to the dataset."""
        check_activity_write(self.session, user, activity_id)
        self._require_activity(activity_id)
        self._require_dataset(dataset_id, user)

        existing = self.session.get(ActivityInput, (activity_id, dataset_id))
        if existing:
            return existing
        link = ActivityInput(activity=activity_id, dataset=dataset_id)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_input(
        self, *, activity_id: int, dataset_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an input dataset from an Activity. Requires write access to the
        Activity."""
        check_activity_write(self.session, user, activity_id)
        link = self.session.get(ActivityInput, (activity_id, dataset_id))
        if not link:
            raise ResourceNotFoundError(
                f"Dataset {dataset_id} is not an input of Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_inputs(
        self,
        activity_id: int,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Dataset]:
        """List the datasets an Activity used as inputs."""
        self.get_readable_or_raise(activity_id, user)
        statement = (
            select(Dataset)
            .join(ActivityInput, col(ActivityInput.dataset) == col(Dataset.id))
            .where(ActivityInput.activity == activity_id)
            .order_by(col(Dataset.id))
        )
        return read_page(
            self.session, Dataset, statement, user, offset=offset, limit=limit
        )

    def add_instrument(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> ActivityInstrument:
        """Add an instrument (a kind=instrument Source) the Activity used.

        Idempotent. Requires write access to the Activity and read access to
        the Source.
        """
        check_activity_write(self.session, user, activity_id)
        self._require_activity(activity_id)
        self._require_instrument(source_id, user)

        existing = self.session.get(ActivityInstrument, (activity_id, source_id))
        if existing:
            return existing
        link = ActivityInstrument(activity=activity_id, source=source_id)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_instrument(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an instrument from an Activity. Requires write access to the
        Activity."""
        check_activity_write(self.session, user, activity_id)
        link = self.session.get(ActivityInstrument, (activity_id, source_id))
        if not link:
            raise ResourceNotFoundError(
                f"Source {source_id} is not an instrument of Activity {activity_id}"
            )
        self.session.delete(link)
        self.session.commit()
        return True

    def get_instruments(
        self,
        activity_id: int,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Source]:
        """List the instruments an Activity used that ``user`` may read."""
        self.get_readable_or_raise(activity_id, user)
        statement = (
            select(Source)
            .join(ActivityInstrument, col(ActivityInstrument.source) == col(Source.id))
            .where(ActivityInstrument.activity == activity_id)
            .order_by(col(Source.id))
        )
        return read_page(
            self.session, Source, statement, user, offset=offset, limit=limit
        )

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
        be an instrument. Requires write access to the Activity and read access
        to the Source.
        """
        check_activity_write(self.session, user, activity_id)
        activity = self._require_activity(activity_id)
        self._require_agent(source_id, user)
        self._require_distinct_from_executor(source_id, activity.source_id)

        existing = self.session.get(ActivityAgent, (activity_id, source_id))
        if existing:
            existing.role = role
            self.session.add(existing)
            self.session.commit()
            return existing
        link = ActivityAgent(activity=activity_id, source_id=source_id, role=role)
        self.session.add(link)
        self.session.commit()
        return link

    def remove_agent(
        self, *, activity_id: int, source_id: int, user: AuthenticatedUser
    ) -> bool:
        """Unlink an additional agent from an Activity. Requires write access to
        the Activity.

        Refused while a delegation on this activity still names the agent, which
        would leave that edge stranded and unserialisable.
        """
        check_activity_write(self.session, user, activity_id)
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
        self,
        activity_id: int,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ActivityAgent]:
        """List the additional agent associations (with roles) for an Activity,
        those whose Source ``user`` may read."""
        self.get_readable_or_raise(activity_id, user)
        statement = (
            select(ActivityAgent)
            .where(ActivityAgent.activity == activity_id)
            .order_by(col(ActivityAgent.source_id))
        )
        links = self.session.exec(statement).all()
        readable = readable_source_ids(
            self.session, {link.source_id for link in links}, user
        )
        visible = [link for link in links if link.source_id in readable]
        return visible[offset : offset + limit]

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
        differ. Idempotent. Requires write access to the Activity.
        """
        check_activity_write(self.session, user, activity_id)
        activity = self._require_activity(activity_id)
        self._require_delegatable(
            subordinate_source_id,
            responsible_source_id,
            self._associated_source_ids(activity),
            user,
        )

        key = (activity_id, subordinate_source_id, responsible_source_id)
        existing = self.session.get(ActivityDelegation, key)
        if existing:
            return existing
        link = ActivityDelegation(
            activity=activity_id,
            subordinate_source=subordinate_source_id,
            responsible_source=responsible_source_id,
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
        """Remove a delegation edge from an Activity. Requires write access to the
        Activity."""
        check_activity_write(self.session, user, activity_id)
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
        self,
        activity_id: int,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ActivityDelegation]:
        """List the delegation edges (``actedOnBehalfOf``) for an Activity, those
        between Sources ``user`` may read."""
        self.get_readable_or_raise(activity_id, user)
        statement = (
            select(ActivityDelegation)
            .where(ActivityDelegation.activity == activity_id)
            .order_by(
                col(ActivityDelegation.subordinate_source),
                col(ActivityDelegation.responsible_source),
            )
        )
        edges = self.session.exec(statement).all()
        readable = readable_source_ids(
            self.session,
            {e.subordinate_source for e in edges}
            | {e.responsible_source for e in edges},
            user,
        )
        visible = [
            e
            for e in edges
            if e.subordinate_source in readable and e.responsible_source in readable
        ]
        return visible[offset : offset + limit]

    def get_for_source(
        self, source_id: int, offset: int = 0, limit: int = 100
    ) -> Sequence[Activity]:
        """Retrieve all Activities associated with a Source — as the primary
        executor (``source_id``) or as an additional agent (``ActivityAgent``).
        """
        agent_activity_ids = select(ActivityAgent.activity).where(
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
