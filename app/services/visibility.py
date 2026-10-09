from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased
from sqlmodel import Session, and_, cast, col, exists, false, or_, select, tuple_
from sqlmodel.sql.expression import Select, SelectOfScalar

from app.auth.access_control import (
    NO_PARENT,
    EffectivePolicy,
    check_read_with_policy,
    get_effective_policies,
    get_effective_policy,
    read_denial,
    resolve_policy,
)
from app.core.audit import resource_id
from app.core.context import ReadTier, record_restricted_access, record_returned
from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.services.exceptions import ForbiddenError
from app.services.filters import policy_tuple_clause

type Listed = Device | Shot | Dataset | Collection
type PolicyTuple = tuple[AccessLevel | None, list[str] | None, list[str] | None]

_SHOT = aliased(Shot)


@dataclass(frozen=True)
class _Columns:
    """Where a model keeps its policy, and the records it inherits policy from."""

    table: str
    key: tuple[Any, ...]
    policy: tuple[Any, Any, Any]
    device_name: Any | None = None
    shot_id: Any | None = None


_COLUMNS: dict[type, _Columns] = {
    Device: _Columns(
        "device",
        (col(Device.id),),
        (
            col(Device.access_level),
            col(Device.required_scopes),
            col(Device.allowed_idps),
        ),
    ),
    Shot: _Columns(
        "shot",
        (col(Shot.device_name), col(Shot.id)),
        (col(Shot.access_level), col(Shot.required_scopes), col(Shot.allowed_idps)),
        device_name=col(Shot.device_name),
    ),
    Dataset: _Columns(
        "dataset",
        (col(Dataset.id),),
        (
            col(Dataset.access_level),
            col(Dataset.required_scopes),
            col(Dataset.allowed_idps),
        ),
        device_name=col(Dataset.device_name),
        shot_id=col(Dataset.shot_id),
    ),
    Collection: _Columns(
        "collection",
        (col(Collection.id),),
        (
            col(Collection.access_level),
            col(Collection.required_scopes),
            col(Collection.allowed_idps),
        ),
        device_name=col(Collection.device_name),
        shot_id=col(Collection.shot_id),
    ),
}


@dataclass(frozen=True)
class _Combination:
    """One distinct policy among a listing's rows, with the shot policy it inherits."""

    own: PolicyTuple
    device_name: str | None
    shot: PolicyTuple | None


def readable_clause(
    session: Session,
    model: type[Listed],
    user: AuthenticatedUser,
    scope: SelectOfScalar[Any],
) -> ColumnElement[bool]:
    """The rows of ``scope`` that ``user`` may read, as a clause on ``model``.

    A row written after the policies were enumerated matches no clause, so it is
    left out rather than let through.
    """
    readable = _readable(session, model, user, scope)
    return or_(*(match for match, _ in readable)) if readable else false()


def read_page[T: Listed](
    session: Session,
    model: type[T],
    statement: SelectOfScalar[T],
    user: AuthenticatedUser,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[T]:
    """Run an ordered listing ``statement``, keeping only rows ``user`` may read.

    Paging applies after visibility, so a short page is the last.
    """
    readable = _readable(session, model, user, statement)
    if not readable:
        record_returned(0)
        return []
    page = statement.where(or_(*(match for match, _ in readable))).offset(offset)
    if limit is not None:
        page = page.limit(limit)
    rows = list(session.exec(page).all())

    restricted = [
        match
        for match, policy in readable
        if policy.access_level == AccessLevel.RESTRICTED
    ]
    columns = _COLUMNS[model]
    if restricted and rows:
        keys = [
            tuple(getattr(row, column.key) for column in columns.key) for row in rows
        ]
        listed = session.exec(
            Select(*columns.key).where(tuple_(*columns.key).in_(keys), or_(*restricted))
        ).all()
        for row_key in listed:
            record_restricted_access(
                columns.table, resource_id(row_key), ReadTier.LISTED
            )
    record_returned(len(rows))
    return rows


def readable_only[T: Listed](
    session: Session, records: Sequence[T], user: AuthenticatedUser
) -> list[T]:
    """The ``records`` ``user`` may read, for a short list resolved in Python."""
    policies = get_effective_policies(records, session)
    result = []
    for record, policy in zip(records, policies, strict=True):
        try:
            check_read_with_policy(record, policy, user, ReadTier.LISTED)
        except ForbiddenError:
            continue
        result.append(record)
    record_returned(len(result))
    return result


def _readable(
    session: Session,
    model: type[Listed],
    user: AuthenticatedUser,
    scope: SelectOfScalar[Any],
) -> list[tuple[ColumnElement[bool], EffectivePolicy]]:
    """A clause for each policy in ``scope`` that ``user`` may read, with the policy."""
    columns = _COLUMNS[model]
    combinations = _combinations(session, model, columns, scope)
    names = {c.device_name for c in combinations} - {None}
    devices = session.exec(select(Device).where(col(Device.name).in_(names))).all()
    device_policies = {d.name: get_effective_policy(d, session) for d in devices}

    readable = []
    for combination in combinations:
        policy = _policy(combination, device_policies)
        in_shot = combination.shot is not None
        if read_denial(model, policy, user, combination.device_name, in_shot) is None:
            readable.append((_matching(columns, combination), policy))
    return readable


def _combinations(
    session: Session,
    model: type[Listed],
    columns: _Columns,
    scope: SelectOfScalar[Any],
) -> list[_Combination]:
    """The distinct policies among the rows ``scope`` selects."""
    level, scopes, idps = columns.policy
    fields: dict[str, Any] = {
        "level": level,
        "scopes": cast(scopes, JSONB),
        "idps": cast(idps, JSONB),
    }
    if columns.device_name is not None:
        fields["device_name"] = columns.device_name
    if columns.shot_id is not None:
        fields |= {
            "in_shot": columns.shot_id.is_not(None),
            "shot_level": _SHOT.access_level,
            "shot_scopes": cast(_SHOT.required_scopes, JSONB),
            "shot_idps": cast(_SHOT.allowed_idps, JSONB),
        }

    statement = select(
        *(field.label(name) for name, field in fields.items())
    ).select_from(model)
    if columns.shot_id is not None:
        statement = statement.outerjoin(_SHOT, _shot_of(columns))
    in_scope = tuple_(*columns.key).in_(
        scope.with_only_columns(*columns.key).order_by(None)
    )
    rows = session.exec(statement.where(in_scope).distinct()).all()

    return [
        _Combination(
            own=(row.level, row.scopes, row.idps),
            device_name=getattr(row, "device_name", None),
            shot=(
                (row.shot_level, row.shot_scopes, row.shot_idps)
                if getattr(row, "in_shot", False)
                else None
            ),
        )
        for row in rows
    ]


def _policy(
    combination: _Combination, device_policies: dict[str, EffectivePolicy]
) -> EffectivePolicy:
    parent = device_policies.get(combination.device_name or "", NO_PARENT)
    if combination.shot is not None:
        parent = resolve_policy(*combination.shot, parent)
    return resolve_policy(*combination.own, parent)


def _matching(columns: _Columns, combination: _Combination) -> ColumnElement[bool]:
    """The rows holding ``combination``'s policy."""
    clauses = [policy_tuple_clause(*columns.policy, *combination.own)]
    if columns.device_name is not None:
        clauses.append(
            columns.device_name.is_(None)
            if combination.device_name is None
            else columns.device_name == combination.device_name
        )
    if columns.shot_id is not None:
        if combination.shot is None:
            clauses.append(columns.shot_id.is_(None))
        else:
            shot_policy = policy_tuple_clause(
                _SHOT.access_level,
                _SHOT.required_scopes,
                _SHOT.allowed_idps,
                *combination.shot,
            )
            clauses.append(exists().where(_shot_of(columns), shot_policy))
    return and_(*clauses)


def _shot_of(columns: _Columns) -> ColumnElement[bool]:
    return and_(_SHOT.device_name == columns.device_name, _SHOT.id == columns.shot_id)
