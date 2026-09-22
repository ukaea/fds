from typing import Any

from sqlalchemy import ColumnElement, case, literal_column, or_
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


def _value_candidates(value: str) -> list[str]:
    """Forms a query-string value might take in stored JSON, as text.

    Query parameters are always strings, but a stored property value keeps its JSON
    type, so ``?annotation=disruption:true`` must still match a stored ``true``.
    Comparison happens on the JSON value rendered as text (``->>``), so each
    candidate is the text PostgreSQL produces for that form: a stored ``true``
    reads as ``true``, a stored ``12`` as ``12``, a stored ``1.50`` as ``1.5``.
    Rather than guess the provider's intended type, match against the raw string
    *or* its coerced form. Matching more broadly avoids false negatives; the cost is
    that ``:true`` would also match a stored ``1``, which is acceptable while values
    are an open vocabulary.
    """
    candidates: list[str] = [value]
    lowered = value.lower()

    if lowered in ("true", "false"):
        candidates.append(lowered)
    else:
        try:
            candidates.append(str(int(value)))
        except ValueError:
            try:
                candidates.append(str(float(value)))
            except ValueError:
                pass

    return list(dict.fromkeys(candidates))


def annotation_clause(
    column: Any, name: str, value: str | None = None
) -> ColumnElement[bool]:
    """Build an EXISTS over the JSON array in ``column`` matching one annotation.

    ``column`` is a ``scientific_metadata`` column on Shot or Dataset. A NULL
    column yields no rows rather than an error, so unannotated records simply do not
    match.

    Each call builds its own ``json_array_elements`` so that several clauses can be
    ANDed together in one query without aliasing into each other.

    An unannotated record holds SQL NULL or a JSON ``null``, and
    ``json_array_elements`` rejects anything that is not an array, so the column is
    replaced by an empty array unless it really is one. Such a record then matches
    nothing instead of raising.
    """
    array_only = case(
        (func.json_typeof(column) == "array", column),
        else_=literal_column("'[]'::json"),
    )
    entries = func.json_array_elements(array_only).table_valued("value")
    entry = entries.c.value
    conditions = [entry.op("->>")("name") == name]

    if value is not None:
        extracted = entry.op("->>")("value")
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
