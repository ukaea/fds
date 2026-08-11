from typing import Any

from sqlalchemy import ColumnElement, or_
from sqlalchemy import select as sa_select
from sqlalchemy.sql.expression import func

from app.services.exceptions import FDSValidationError

ANNOTATION_SEPARATOR = ":"


def parse_annotation(raw: str) -> tuple[str, str | None]:
    """Split an ``annotation`` query parameter into a name and optional value.

    Splits on the *first* separator only, so a value may itself contain one
    (``mode:n=1:tearing`` is the value ``n=1:tearing``).

    Returns ``(name, None)`` for a presence filter, ``(name, value)`` for equality.
    """
    name, separator, value = raw.partition(ANNOTATION_SEPARATOR)

    if not name:
        raise FDSValidationError(
            f"Invalid annotation filter '{raw}': expected 'name' or "
            f"'name{ANNOTATION_SEPARATOR}value'."
        )
    if separator and not value:
        raise FDSValidationError(
            f"Invalid annotation filter '{raw}': a value is expected after "
            f"'{ANNOTATION_SEPARATOR}'. Omit the separator to filter on presence "
            "alone."
        )

    return name, (value if separator else None)


def _value_candidates(value: str) -> list[Any]:
    """Forms a query-string value might take in stored JSON.

    Query parameters are always strings, but a stored property value keeps its JSON
    type, so ``?annotation=disruption:true`` must still match a stored ``true``.
    Rather than guess the provider's intended type, match against the raw string
    *or* its coerced form. Matching more broadly avoids false negatives; the cost is
    that ``:true`` would also match a stored ``1``, which is acceptable while values
    are an open vocabulary.
    """
    candidates: list[Any] = [value]
    lowered = value.lower()

    if lowered == "true":
        candidates.append(True)
    elif lowered == "false":
        candidates.append(False)
    else:
        try:
            candidates.append(int(value))
        except ValueError:
            try:
                candidates.append(float(value))
            except ValueError:
                pass

    return candidates


def annotation_clause(
    column: Any, name: str, value: str | None = None
) -> ColumnElement[bool]:
    """Build an EXISTS over the JSON array in ``column`` matching one annotation.

    ``column`` is a ``scientific_metadata`` column on Shot or Dataset. A NULL
    column yields no rows rather than an error, so unannotated records simply do not
    match.

    Each call builds its own ``json_each`` so that several clauses can be ANDed
    together in one query without aliasing into each other.
    """
    entries = func.json_each(column).table_valued("value")
    conditions = [func.json_extract(entries.c.value, "$.name") == name]

    if value is not None:
        extracted = func.json_extract(entries.c.value, "$.value")
        conditions.append(or_(*(extracted == c for c in _value_candidates(value))))

    return sa_select(1).select_from(entries).where(*conditions).exists()


def annotation_clauses(
    column: Any, annotations: list[str] | None
) -> list[ColumnElement[bool]]:
    """Parse and build a clause per annotation. Repeated values AND together."""
    if not annotations:
        return []
    return [
        annotation_clause(column, *parse_annotation(annotation))
        for annotation in annotations
    ]
