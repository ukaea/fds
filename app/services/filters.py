from typing import Any

from sqlalchemy import (
    ColumnElement,
    Numeric,
    and_,
    case,
    cast,
    literal,
    literal_column,
    or_,
)
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.expression import func

from app.models.policy import AccessLevel
from app.services.exceptions import FDSValidationError

PROPERTY_SEPARATOR = ":"


def parse_property(raw: str) -> tuple[str, str | None]:
    """Split an ``property`` query parameter into a name and optional value.

    Splits on the *first* separator only, so a value may itself contain one
    (``mode:n=1:tearing`` is the value ``n=1:tearing``).

    Returns ``(name, None)`` for a presence filter, ``(name, value)`` for equality.
    """
    name, separator, value = raw.partition(PROPERTY_SEPARATOR)

    if not name:
        raise FDSValidationError(
            f"Invalid property filter '{raw}': expected 'name' or "
            f"'name{PROPERTY_SEPARATOR}value'."
        )
    if separator and not value:
        raise FDSValidationError(
            f"Invalid property filter '{raw}': a value is expected after "
            f"'{PROPERTY_SEPARATOR}'. Omit the separator to filter on presence "
            "alone."
        )

    return name, (value if separator else None)


def _value_candidates(value: str) -> list[str]:
    """Forms a query-string value might take in stored JSON, as text.

    Query parameters are always strings, but a stored property value keeps its JSON
    type, so ``?property=disruption:true`` must still match a stored ``true``.
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


def entries_of(column: Any) -> Any:
    """The JSON array in ``column`` as a set of entries, one row per property.

    A NULL column, a JSON ``null`` or a scalar yields no entries rather than an
    error, because ``json_array_elements`` rejects anything that is not an
    array. An unannotated record therefore matches nothing instead of raising.

    Built fresh on each call: two ``json_array_elements`` in one statement would
    otherwise alias into each other.
    """
    array_only = case(
        (func.json_typeof(column) == "array", column),
        else_=literal_column("'[]'::json"),
    )
    return func.json_array_elements(array_only).table_valued("value")


def property_clause(
    column: Any, name: str, value: str | None = None
) -> ColumnElement[bool]:
    """Build an EXISTS over the JSON array in ``column`` matching one property.

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
    entries = entries_of(column)
    entry = entries.c.value
    conditions = [entry.op("->>")("name") == name]

    if value is not None:
        extracted = entry.op("->>")("value")
        conditions.append(or_(*(extracted == c for c in _value_candidates(value))))

    return sa_select(1).select_from(entries).where(*conditions).exists()


def property_clauses(
    column: Any, properties: list[str] | None
) -> list[ColumnElement[bool]]:
    """Parse and build the clauses for a set of ``property`` parameters.

    Values of the **same** name OR together; **different** names AND. So
    ``?property=heating:SS&property=heating:SW&property=pellets:true``
    asks for (SS or SW) and pellets, which is what selecting two chips in one
    prop and one in another means.

    This is the convention faceted search settled on, and the one ESGF uses for
    the same shape of catalogue. Requiring several values of one name
    simultaneously is a different question, and a richer one; it belongs with
    the extent predicates in a structured search rather than in a query string.

    A bare name still means presence, and mixing presence with values under one
    name ORs them too: a record carrying the name at all satisfies the presence
    term.
    """
    if not properties:
        return []

    by_name: dict[str, list[str | None]] = {}
    for prop in properties:
        name, value = parse_property(prop)
        by_name.setdefault(name, []).append(value)

    clauses: list[ColumnElement[bool]] = []
    for name, values in by_name.items():
        alternatives = [property_clause(column, name, value) for value in values]
        clauses.append(
            alternatives[0] if len(alternatives) == 1 else or_(*alternatives)
        )
    return clauses


def parse_property_bound(raw: str) -> tuple[str, float]:
    """Split an ``property_min``/``property_max`` parameter into name and number.

    Same ``name:value`` shape as ``property``, but the value has to be a
    number: a range over a value that is not a magnitude means nothing.
    """
    name, separator, value = raw.partition(PROPERTY_SEPARATOR)
    if not name or not separator or not value:
        raise FDSValidationError(
            f"Invalid range filter '{raw}': expected 'name{PROPERTY_SEPARATOR}number'."
        )
    try:
        return name, float(value)
    except ValueError:
        raise FDSValidationError(
            f"Invalid range filter '{raw}': '{value}' is not a number."
        ) from None


def property_bound_clause(
    column: Any, name: str, bound: float, *, lower: bool
) -> ColumnElement[bool]:
    """Match records whose numeric value for ``name`` is at or beyond ``bound``.

    ``scientific_metadata`` values are arbitrary JSON, so a name may hold a
    number on one record and a string on another. The comparison is guarded to
    numeric-looking values, because casting a stray string to numeric aborts the
    whole query rather than skipping the row.
    """
    entries = entries_of(column)
    entry = entries.c.value
    extracted = entry.op("->>")("value")
    numeric = cast(extracted, Numeric)
    conditions: list[ColumnElement[bool]] = [
        entry.op("->>")("name") == name,
        extracted.op("~")(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$"),
        numeric >= bound if lower else numeric <= bound,
    ]
    return sa_select(1).select_from(entries).where(*conditions).exists()


def property_bound_clauses(
    column: Any, bounds: list[str] | None, *, lower: bool
) -> list[ColumnElement[bool]]:
    """Parse and build a clause per range bound. Bounds AND together."""
    if not bounds:
        return []
    return [
        property_bound_clause(column, *parse_property_bound(bound), lower=lower)
        for bound in bounds
    ]


def policy_tuple_clause(
    access_level_column: Any,
    scopes_column: Any,
    idps_column: Any,
    access_level: AccessLevel | None,
    required_scopes: list[str] | None,
    allowed_idps: list[str] | None,
) -> ColumnElement[bool]:
    """Match rows whose stored policy tuple is exactly this one.

    Null means "inherit from the parent", not "no value", so a null component
    is matched by absence rather than equality. Equality would never match an
    inheriting row, which is the most common policy of all.

    Absence has two spellings and both occur. SQLAlchemy's ``JSON`` type
    serialises a Python ``None`` to a JSON ``null`` rather than SQL NULL, so an
    unset ``required_scopes`` is almost always the JSON one; SQL NULL appears in
    rows written by other paths. ``IS NULL`` alone matches only the second and
    would exclude nearly every row, so both are tested.

    ``required_scopes`` and ``allowed_idps`` are ``JSON`` columns, and
    PostgreSQL gives ``json`` no equality operator, so comparing a set has to go
    through ``jsonb``. That cast also canonicalises, so two spellings of one list
    compare equal instead of forming two tuples.
    """
    conditions: list[ColumnElement[bool]] = []

    if access_level is None:
        conditions.append(access_level_column.is_(None))
    else:
        conditions.append(access_level_column == access_level)

    for column, value in (
        (scopes_column, required_scopes),
        (idps_column, allowed_idps),
    ):
        if value is None:
            conditions.append(or_(column.is_(None), func.json_typeof(column) == "null"))
        else:
            conditions.append(cast(column, JSONB) == literal(value, JSONB))

    return and_(*conditions)
