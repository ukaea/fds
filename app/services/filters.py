from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import (
    Numeric,
    and_,
    case,
    cast,
    col,
    func,
    literal,
    literal_column,
    or_,
    select,
    true,
)

from app.models.activity import Activity, ActivityType
from app.models.policy import AccessLevel
from app.models.scientific_metadata import PATH_SEPARATOR, PROPERTY_SEPARATOR
from app.models.scope import CatalogueScope, DeviceScope
from app.models.source import Source
from app.services.exceptions import FDSValidationError


def parse_property(raw: str) -> tuple[str, str | None]:
    """Split a ``property`` query parameter into a path and optional value.

    The path names a property, or a property inside a group with the names
    joined by ``.``: ``coolant.type``. Splits on the *first* separator only, so
    a value may itself contain one (``mode:n=1:tearing`` is the value
    ``n=1:tearing``). A name cannot contain one, so the first always ends the
    path.

    Returns ``(path, None)`` for a presence filter, ``(path, value)`` for
    equality.
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


def _array_or_empty(value: Any) -> Any:
    """``value`` when it is a JSON array, and an empty array otherwise.

    ``json_array_elements`` rejects anything that is not an array. A record
    with no metadata holds SQL NULL or a JSON ``null``, and a property that is
    not a group holds no ``properties``, so each yields no rows instead of
    raising.
    """
    return case(
        (func.json_typeof(value) == "array", value),
        else_=literal_column("'[]'::json"),
    )


def _properties_in(array: Any) -> Any:
    """The properties in a JSON array, one row each, in a column named ``value``.

    Built fresh on each call: two ``json_array_elements`` in one statement would
    otherwise alias into each other.
    """
    return func.json_array_elements(_array_or_empty(array)).table_valued("value")


def _is_group(entry: Any) -> ColumnElement[bool]:
    """Whether a property holds a list of properties rather than a value."""
    return func.json_typeof(entry.op("->")("properties")).is_not_distinct_from("array")


def property_entries(column: Any, path: str | None = None) -> Any:
    """The properties in a ``scientific_metadata`` column, one row each.

    Each row has the property's ``path`` (its name, after the names of the
    groups it sits in, joined by ``.``), the property itself as JSON in
    ``entry``, the ``extent`` that localises it, and whether it ``is_group``.
    A property inside a group has no extent of its own, so it carries the
    extent of the outermost group it sits in.

    With no ``path``, every property at every depth is returned, for the
    properties summary. With a ``path``, only the properties at that path are,
    found by following its names down through each group's ``properties``.
    Following one path costs about what reading a flat list does, and walking
    every depth to find it costs several times more, so a filter, which names
    one path, follows it. Both read a group's children with ``_properties_in``,
    so they cannot disagree about where the children are.

    Returned as a lateral subquery, to join to the table ``column`` belongs to
    or to select from inside an EXISTS.
    """
    if path is not None:
        return _entries_at(column, path)

    top = _properties_in(column)
    walk = select(
        top.c.value.op("->>")("name").label("path"),
        top.c.value.label("entry"),
        top.c.value.op("->")("extent").label("extent"),
    ).cte(recursive=True, nesting=True)
    children = _properties_in(walk.c.entry.op("->")("properties"))
    walk = walk.union_all(
        select(
            func.concat(
                walk.c.path, PATH_SEPARATOR, children.c.value.op("->>")("name")
            ),
            children.c.value,
            walk.c.extent,
        )
        .select_from(walk)
        .join(children, true())
    )
    return select(
        walk.c.path,
        walk.c.entry,
        walk.c.extent,
        _is_group(walk.c.entry).label("is_group"),
    ).lateral()


def _entries_at(column: Any, path: str) -> Any:
    """The properties at ``path``, in the shape ``property_entries`` returns."""
    names = path.split(PATH_SEPARATOR)
    levels = [_properties_in(column)]
    for _ in names[1:]:
        levels.append(_properties_in(levels[-1].c.value.op("->")("properties")))
    top, bottom = levels[0], levels[-1]

    statement = select(
        literal(path).label("path"),
        bottom.c.value.label("entry"),
        top.c.value.op("->")("extent").label("extent"),
        _is_group(bottom.c.value).label("is_group"),
    ).select_from(top)
    for level in levels[1:]:
        statement = statement.join(level, true())
    return statement.where(
        *(
            level.c.value.op("->>")("name") == name
            for level, name in zip(levels, names, strict=True)
        )
    ).lateral()


def property_clause(
    column: Any, path: str, value: str | None = None
) -> ColumnElement[bool]:
    """Build an EXISTS matching records that carry a property at ``path``.

    ``column`` is a ``scientific_metadata`` column. Without a ``value``, any
    property at the path matches, a group included. With one, the property's
    value has to match, so a group, which has no value, never does.

    Each call builds its own subquery, so several clauses can be ANDed together
    in one query without aliasing into each other.
    """
    entries = property_entries(column, path)
    conditions: list[ColumnElement[bool]] = []

    if value is not None:
        extracted = entries.c.entry.op("->>")("value")
        conditions.append(or_(*(extracted == c for c in _value_candidates(value))))

    return sa_select(1).select_from(entries).where(*conditions).exists()


def property_clauses(
    column: Any, properties: list[str] | None
) -> list[ColumnElement[bool]]:
    """Parse and build the clauses for a set of ``property`` parameters.

    Values of the **same** path OR together; **different** paths AND. So
    ``?property=heating:SS&property=heating:SW&property=pellets:true``
    asks for (SS or SW) and pellets, which is what selecting two chips in one
    prop and one in another means.

    This is the convention faceted search settled on, and the one ESGF uses for
    the same shape of catalogue. Requiring several values of one name
    simultaneously is a different question, and a richer one; it belongs with
    the extent predicates in a structured search rather than in a query string.

    A bare path still means presence, and mixing presence with values under one
    path ORs them too: a record carrying the path at all satisfies the presence
    term.

    In a group that repeats, each clause is matched against every instance on
    its own. ``coolant.thermocouple.id:T1`` and
    ``coolant.thermocouple.max:850`` match a shot where one thermocouple is
    T1 and another reached 850.
    """
    if not properties:
        return []

    by_path: dict[str, list[str | None]] = {}
    for prop in properties:
        path, value = parse_property(prop)
        by_path.setdefault(path, []).append(value)

    clauses: list[ColumnElement[bool]] = []
    for path, values in by_path.items():
        alternatives = [property_clause(column, path, value) for value in values]
        clauses.append(
            alternatives[0] if len(alternatives) == 1 else or_(*alternatives)
        )
    return clauses


def parse_property_bound(raw: str) -> tuple[str, float]:
    """Split a ``property_min``/``property_max`` parameter into path and number.

    Same ``path:value`` shape as ``property``, but the value has to be a
    number: a range over a value that is not a magnitude means nothing.
    """
    path, separator, value = raw.partition(PROPERTY_SEPARATOR)
    if not path or not separator or not value:
        raise FDSValidationError(
            f"Invalid range filter '{raw}': expected 'name{PROPERTY_SEPARATOR}number'."
        )
    try:
        return path, float(value)
    except ValueError:
        raise FDSValidationError(
            f"Invalid range filter '{raw}': '{value}' is not a number."
        ) from None


def property_bound_clause(
    column: Any, path: str, bound: float, *, lower: bool
) -> ColumnElement[bool]:
    """Match records whose numeric value at ``path`` is at or beyond ``bound``.

    A path may hold a number on one record and a string on another. The
    comparison is guarded to numeric-looking values, because casting a stray
    string to numeric aborts the whole query rather than skipping the row.
    """
    entries = property_entries(column, path)
    extracted = entries.c.entry.op("->>")("value")
    numeric = cast(extracted, Numeric)
    conditions: list[ColumnElement[bool]] = [
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


def scope_clauses(
    device_column: Any, shot_column: Any, scope: CatalogueScope | DeviceScope
) -> list[ColumnElement[bool]]:
    """The clauses that keep only the kind of record ``scope`` asks for.

    A global record names no device, a device-level record names a device but no
    shot, and a shot-level record names both. Which device a listing is under is
    left to its own clauses, so ``DEVICE`` means the same under a device as at
    the root.
    """
    match CatalogueScope(scope.value):
        case CatalogueScope.GLOBAL:
            return [device_column.is_(None)]
        case CatalogueScope.DEVICE:
            return [device_column.is_not(None), shot_column.is_(None)]
        case CatalogueScope.SHOT:
            return [shot_column.is_not(None)]
        case CatalogueScope.ALL:
            return []


def shot_id_prefix_clauses(
    shot_column: Any, shot_id_prefix: str | None
) -> list[ColumnElement[bool]]:
    """Keep the records on a shot whose ID starts with ``shot_id_prefix``.

    ``304`` keeps the records on shots 30420 and 30421 but not on 30520. A record
    on no shot never matches.
    """
    if not shot_id_prefix:
        return []
    return [shot_column.startswith(shot_id_prefix, autoescape=True)]


def activity_clauses(
    activity_column: Any,
    activity_type: ActivityType | None = None,
    source: str | None = None,
    activity_id: int | None = None,
) -> list[ColumnElement[bool]]:
    """Narrow a listing by the Activity each record names in its ``activity_id``.

    ``activity_id`` keeps the records of one Activity. ``activity_type`` keeps
    those whose Activity was of that type, and ``source`` those whose Activity
    was carried out by the source with that name. A record with no
    ``activity_id`` matches none of them.

    For a dataset, that Activity is the one that generated it. For a collection,
    it is the Activity the collection bundles, whose members may include datasets
    the Activity did not generate, such as its inputs. Only the collection's own
    ``activity_id`` is matched, not its members'.
    """
    clauses: list[ColumnElement[bool]] = []
    if activity_id is not None:
        clauses.append(activity_column == activity_id)
    if activity_type is not None:
        of_type = select(Activity.id).where(Activity.activity_type == activity_type)
        clauses.append(activity_column.in_(of_type))
    if source is not None:
        by_source = (
            select(Activity.id)
            .join(Source, col(Source.id) == col(Activity.source_id))
            .where(Source.name == source)
        )
        clauses.append(activity_column.in_(by_source))
    return clauses
