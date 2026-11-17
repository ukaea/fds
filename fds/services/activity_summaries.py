from collections.abc import Iterable

from sqlmodel import Session, col, select

from fds.models.activity import Activity, ActivitySummary
from fds.models.source import Source


def activity_summaries(
    session: Session, activity_ids: Iterable[int | None]
) -> dict[int, ActivitySummary]:
    """Summaries of the Activities ``activity_ids`` name, by id, read in one query.

    Dataset and collection reads include these. Callers pass only the ids of
    records the user may read, so a summary appears only where its record does.
    """
    ids = {i for i in activity_ids if i is not None}
    if not ids:
        return {}
    rows = session.exec(
        select(Activity, Source.name)
        .outerjoin(Source, col(Source.id) == col(Activity.source_id))
        .where(col(Activity.id).in_(ids))
    ).all()
    return {
        activity.id: ActivitySummary(
            activity_type=activity.activity_type,
            source=source,
            source_version=activity.source_version,
            started_at=activity.started_at,
        )
        for activity, source in rows
        if activity.id is not None
    }
