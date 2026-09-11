from collections.abc import Sequence
from enum import Enum

import structlog
from sqlalchemy import event
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm.attributes import instance_state
from sqlmodel import SQLModel

from app.core.context import ReadTier, get_actor, record_restricted_access
from app.models.policy import AccessLevel

logger = structlog.get_logger("fds.audit")

# Recorded with their before and after values. Everything else contributes its
# name to changed_fields and nothing more, so descriptions and scientific
# metadata stay out of the log and the line stays a bounded size.
POLICY_FIELDS = ("access_level", "required_scopes", "allowed_idps")

# The listener sees table writes, not API calls, so link-table rows are named
# after the operation that produces them. Anything absent falls back to
# "<table>.<operation>".
ACTIONS: dict[tuple[str, str], str] = {
    ("collectiondataset", "insert"): "collection.add_dataset",
    ("collectiondataset", "delete"): "collection.remove_dataset",
    ("collectionmember", "insert"): "collection.add_child",
    ("collectionmember", "delete"): "collection.remove_child",
    ("datasetderivation", "insert"): "dataset.add_derivation",
    ("datasetderivation", "delete"): "dataset.remove_derivation",
    ("activityinput", "insert"): "activity.add_input",
    ("activityinstrument", "insert"): "activity.add_instrument",
    ("activityagent", "insert"): "activity.add_agent",
    ("activitydelegation", "insert"): "activity.add_delegation",
}

_PENDING = "fds_audit_pending"


def _identity(obj: SQLModel) -> dict[str, object]:
    """The columns that say which row this is."""
    fields: dict[str, object] = {}
    for column in class_mapper(type(obj)).primary_key:
        fields[column.name] = getattr(obj, column.name, None)
    if hasattr(obj, "name"):
        fields["name"] = getattr(obj, "name")
    return fields


def _changes(obj: SQLModel) -> tuple[list[str], dict[str, object]]:
    """Changed column names, and before/after values for policy fields."""
    changed: list[str] = []
    values: dict[str, object] = {}
    state = instance_state(obj)
    for attr in state.attrs:
        history = attr.history
        if not history.has_changes():
            continue
        changed.append(attr.key)
        if attr.key in POLICY_FIELDS:
            values[f"{attr.key}_before"] = _scalar(history.deleted)
            values[f"{attr.key}_after"] = _scalar(history.added)
    return changed, values


def _scalar(values: Sequence[object]) -> object:
    """The single value from a history side, with enums unwrapped for JSON."""
    if not values:
        return None
    value = values[0]
    return value.value if isinstance(value, Enum) else value


def _record(obj: SQLModel, operation: str) -> dict[str, object]:
    table = type(obj).__tablename__  # type: ignore[attr-defined]
    record: dict[str, object] = {
        "action": ACTIONS.get((str(table), operation), f"{table}.{operation}"),
        "resource_type": str(table),
        "operation": operation,
        **_identity(obj),
    }
    if operation == "update":
        changed, values = _changes(obj)
        record["changed_fields"] = changed
        record.update(values)
    return record


@event.listens_for(SASession, "after_flush")
def collect_mutations(session: SASession, _flush_context: object):
    """Gather what was written, holding it until the transaction commits.

    After the flush rather than before, because a new row has no primary key
    until then. The session still reports its pre-flush state here, so the
    attribute history is intact.
    """
    pending: list[dict[str, object]] = session.info.setdefault(_PENDING, [])
    for obj in session.new:
        if isinstance(obj, SQLModel):
            pending.append(_record(obj, "insert"))
    for obj in session.dirty:
        if isinstance(obj, SQLModel) and session.is_modified(obj):
            pending.append(_record(obj, "update"))
    for obj in session.deleted:
        if isinstance(obj, SQLModel):
            pending.append(_record(obj, "delete"))


@event.listens_for(SASession, "after_commit")
def emit_mutations(session: SASession):
    """Emit one line per write, once the transaction has actually committed."""
    pending: list[dict[str, object]] = session.info.pop(_PENDING, [])
    actor = get_actor()
    for record in pending:
        logger.info(
            record.pop("action"),
            actor_id=actor.id if actor else None,
            **record,
        )


@event.listens_for(SASession, "after_rollback")
@event.listens_for(SASession, "after_soft_rollback")
def discard_mutations(session: SASession, _previous: object = None):
    """A write that was rolled back did not happen."""
    session.info.pop(_PENDING, None)


def record_restricted_read(
    obj: SQLModel, access_level: AccessLevel | None, tier: ReadTier
) -> None:
    if access_level != AccessLevel.RESTRICTED:
        return
    identity = _identity(obj)
    resource_id = next(iter(identity.values()), None)
    if isinstance(resource_id, int):
        record_restricted_access(str(type(obj).__tablename__), resource_id, tier)


def record_data_access(
    dataset_id: int | None,
    url: str,
    endpoint_url: str | None,
    access_level: AccessLevel | None,
) -> None:
    """Record that storage credentials were vended for a dataset's data."""
    logger.info(
        "data.access",
        resource_type="dataset",
        dataset_id=dataset_id,
        url=url,
        endpoint_url=endpoint_url,
        access_level=access_level.value if access_level else None,
        actor_id=(actor.id if (actor := get_actor()) else None),
    )
