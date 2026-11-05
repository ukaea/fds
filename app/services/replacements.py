from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import ColumnElement
from sqlmodel import Session, col, select

from app.models.collection import Collection, CollectionReplacement
from app.models.dataset import Dataset, DatasetReplacement
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.services.exceptions import FDSValidationError, ResourceNotFoundError
from app.services.visibility import readable_clause, readable_only

type Record = type[Dataset | Collection]
type Link = type[DatasetReplacement | CollectionReplacement]


def not_replaced(
    session: Session, record: Record, link: Link, user: AuthenticatedUser
) -> ColumnElement[bool]:
    """A query condition that keeps a record unless ``user`` may read a record
    that replaces it.

    A record whose replacements ``user`` may not read is kept: for them it is
    the newest version.
    """
    replacing = select(record).join(link, col(link.replacement) == col(record.id))
    replaced_for_user = (
        select(col(link.replaced))
        .join(record, col(record.id) == col(link.replacement))
        .where(readable_clause(session, record, user, replacing))
        .correlate(None)
    )
    return col(record.id).not_in(replaced_for_user)


def check_replaces(
    session: Session,
    record: Record,
    link: Link,
    replaces: Iterable[int],
    *,
    device_name: str | None,
    shot_id: str | None,
    record_id: int | None = None,
) -> None:
    """Check that a record may replace each record in ``replaces``.

    Each must exist and be filed in the same device and shot. A record cannot
    replace itself, or a record that already replaces it, directly or through
    others. ``record_id`` is the replacing record's own id, None while it is
    being registered, when nothing can replace it yet.
    """
    kind = record.__name__
    replaces = list(replaces)
    for replaced_id in replaces:
        if replaced_id == record_id:
            raise FDSValidationError(f"A {kind.lower()} cannot replace itself")
        replaced = session.get(record, replaced_id)
        if replaced is None:
            raise ResourceNotFoundError(f"{kind} {replaced_id} not found")
        if (replaced.device_name, replaced.shot_id) != (device_name, shot_id):
            raise FDSValidationError(
                f"{kind} {replaced_id} is filed under a different device or shot. "
                f"A {kind.lower()} can only replace one filed in the same place."
            )
    if record_id is None:
        return
    later = later_versions(session, link, record_id)
    for replaced_id in replaces:
        if replaced_id in later:
            raise FDSValidationError(
                f"{kind} {replaced_id} already replaces {kind.lower()} {record_id}, "
                "so it cannot be replaced by it"
            )


def later_versions(session: Session, link: Link, record_id: int) -> set[int]:
    """The ids of the records that replace ``record_id``, directly or through
    others. Records already found are skipped, so the walk ends even if the
    links form a loop."""
    found: set[int] = set()
    frontier = {record_id}
    while frontier:
        replacing = session.exec(
            select(link.replacement).where(col(link.replaced).in_(frontier))
        ).all()
        frontier = set(replacing) - found - {record_id}
        found |= frontier
    return found


def replaced_ids(session: Session, link: Link, record_id: int) -> set[int]:
    """The ids of the records ``record_id`` replaces directly."""
    return set(
        session.exec(
            select(link.replaced).where(col(link.replacement) == record_id)
        ).all()
    )


def write_replaces(
    session: Session, link: Link, record_id: int, replaces: set[int]
) -> None:
    """Make ``replaces`` the set of records ``record_id`` replaces. Not committed."""
    current = replaced_ids(session, link, record_id)
    for row in session.exec(
        select(link).where(
            col(link.replacement) == record_id,
            col(link.replaced).in_(current - replaces),
        )
    ).all():
        session.delete(row)
    for replaced in replaces - current:
        session.add(link(replacement=record_id, replaced=replaced))


def replaces_and_replaced_by(
    session: Session,
    record: Record,
    link: Link,
    records: Sequence[Dataset] | Sequence[Collection],
    user: AuthenticatedUser | None,
) -> dict[int | None, tuple[list[int], list[int]]]:
    """For each of ``records``, by id, two lists: the ids of the records it
    replaces, and the ids of the records replacing it that ``user`` may read.
    Read in one query.

    Replacements ``user`` may not read are left out, since naming them would
    tell the reader they exist.
    """
    ids = {r.id for r in records}
    if not ids:
        return {}
    links = session.exec(
        select(link, record)
        .join(record, col(record.id) == col(link.replacement))
        .where(col(link.replacement).in_(ids) | col(link.replaced).in_(ids))
        .order_by(col(link.replacement), col(link.replaced))
    ).all()
    replacing = [replacer for row, replacer in links if row.replaced in ids]
    readable = {r.id for r in readable_only(session, replacing, user or ANONYMOUS_USER)}
    result: defaultdict[int | None, tuple[list[int], list[int]]] = defaultdict(
        lambda: ([], [])
    )
    for row, _ in links:
        if row.replacement in ids:
            result[row.replacement][0].append(row.replaced)
        if row.replaced in ids and row.replacement in readable:
            result[row.replaced][1].append(row.replacement)
    return result
