from collections.abc import Sequence
from dataclasses import dataclass, replace
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
    joined by ``.``: ``nbi.beam.source``. Splits on the *first* separator only, so
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


# Matches the text PostgreSQL renders for a JSON number.
NUMERIC_TEXT = r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$"


@dataclass(frozen=True)
class PropertyCondition:
    """One ``property``, ``property_min`` or ``property_max`` parameter, parsed.

    ``names`` is the path split into its names. With neither ``value`` nor
    ``bound`` the condition asks only that the property is there. ``value``
    asks for that value, and ``bound`` for a number at or above it when
    ``lower``, at or below it otherwise.
    """

    names: tuple[str, ...]
    value: str | None = None
    bound: float | None = None
    lower: bool = True


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


def property_conditions(
    properties: list[str] | None = None,
    minimums: list[str] | None = None,
    maximums: list[str] | None = None,
) -> list[PropertyCondition]:
    """Parse the ``property``, ``property_min`` and ``property_max`` parameters."""
    conditions = []
    for raw in properties or []:
        path, value = parse_property(raw)
        conditions.append(
            PropertyCondition(tuple(path.split(PATH_SEPARATOR)), value=value)
        )
    for bounds, lower in ((minimums, True), (maximums, False)):
        for raw in bounds or []:
            path, bound = parse_property_bound(raw)
            conditions.append(
                PropertyCondition(
                    tuple(path.split(PATH_SEPARATOR)), bound=bound, lower=lower
                )
            )
    return conditions


def _meets(condition: PropertyCondition, entry: Any) -> ColumnElement[bool]:
    """Whether the property ``entry`` meets ``condition``, its name aside.

    A bound compares only values that read as numbers: the CASE leaves any
    other value NULL, where casting it would abort the whole query.
    """
    value = entry.op("->>")("value")
    if condition.bound is not None:
        number = case((value.op("~")(NUMERIC_TEXT), cast(value, Numeric)))
        return (
            number >= condition.bound if condition.lower else number <= condition.bound
        )
    if condition.value is None:
        return true()
    return or_(*(value == c for c in _value_candidates(condition.value)))


def _clauses_on(
    array: Any, conditions: Sequence[PropertyCondition]
) -> list[ColumnElement[bool]]:
    """The clauses the properties in a JSON ``array`` must meet for ``conditions``.

    A condition on a property in the array is met by any property of that name.
    Presence and values of one name are alternatives and OR together, and each
    bound is a clause of its own. The conditions on properties inside a group
    must all be met by one entry of the group, so they go in a single EXISTS
    over the group's entries, built the same way one level down.
    """
    here: dict[str, list[PropertyCondition]] = {}
    inside: dict[str, list[PropertyCondition]] = {}
    for condition in conditions:
        named = here if len(condition.names) == 1 else inside
        named.setdefault(condition.names[0], []).append(condition)

    clauses: list[ColumnElement[bool]] = []
    for name, named_here in here.items():
        alternatives = [c for c in named_here if c.bound is None]
        if alternatives:
            entries = _properties_in(array)
            entry = entries.c.value
            clauses.append(
                sa_select(1)
                .select_from(entries)
                .where(
                    entry.op("->>")("name") == name,
                    or_(*(_meets(c, entry) for c in alternatives)),
                )
                .exists()
            )
        for bound in (c for c in named_here if c.bound is not None):
            entries = _properties_in(array)
            entry = entries.c.value
            clauses.append(
                sa_select(1)
                .select_from(entries)
                .where(entry.op("->>")("name") == name, _meets(bound, entry))
                .exists()
            )
    for name, named_inside in inside.items():
        instances = _properties_in(array)
        instance = instances.c.value
        within = [replace(c, names=c.names[1:]) for c in named_inside]
        clauses.append(
            sa_select(1)
            .select_from(instances)
            .where(
                instance.op("->>")("name") == name,
                *_clauses_on(instance.op("->")("properties"), within),
            )
            .exists()
        )
    return clauses


def property_clauses(
    column: Any,
    properties: list[str] | None,
    minimums: list[str] | None = None,
    maximums: list[str] | None = None,
) -> list[ColumnElement[bool]]:
    """Parse and build the clauses for the ``property`` filters on a column.

    Values of the **same** path OR together; **different** paths AND. So
    ``?property=heating:SS&property=heating:SW&property=pellets:true``
    asks for (SS or SW) and pellets, which is what selecting two chips in one
    prop and one in another means. A bare path means presence, and mixing it
    with values of the same path ORs them too. ``minimums`` and ``maximums``
    bound numeric values, each bound a condition of its own.

    When several filters name properties in the same group, one entry of that
    group has to match all of them. ``nbi.beam.source:SW`` with a minimum of
    1.5 on ``nbi.beam.power`` asks for a beam that is SW and ran at 1.5 MW or
    more. A shot where the SW beam ran at 1.4 MW while the SS beam ran at
    1.6 MW does not match. Asking about two entries at once, such as two beams
    that both ran above 1.5 MW, belongs with the extent predicates in a
    structured search rather than in a query string.
    """
    return _clauses_on(column, property_conditions(properties, minimums, maximums))


def _group_conditions(
    conditions: Sequence[PropertyCondition],
) -> dict[str, list[PropertyCondition]]:
    """The filters that apply inside each group, keyed by the group's path.

    A filter on ``nbi.beam.power`` applies inside ``nbi``, where it is a filter
    on ``beam.power``, and inside ``nbi.beam``, where it is a filter on
    ``power``.
    """
    by_group: dict[str, list[PropertyCondition]] = {}
    for condition in conditions:
        for depth in range(1, len(condition.names)):
            group = PATH_SEPARATOR.join(condition.names[:depth])
            by_group.setdefault(group, []).append(
                replace(condition, names=condition.names[depth:])
            )
    return by_group


def _in_a_matching_instance(
    path: Any, entry: Any, by_group: dict[str, list[PropertyCondition]]
) -> ColumnElement[bool]:
    """Whether the summary should look at this property, given the filters.

    A group entry is looked at only if it matches the filters that apply
    inside it, and when it is skipped so is everything in it. With a filter on
    ``nbi.beam.source:SW``, the entry for the SS beam is skipped, and with it
    the SS beam's ``power``. Every property that is not a group is looked at.
    """
    if not by_group:
        return true()
    return or_(
        ~_is_group(entry),
        case(
            *(
                (
                    path == group,
                    and_(*_clauses_on(entry.op("->")("properties"), within)),
                )
                for group, within in by_group.items()
            ),
            else_=true(),
        ),
    )


def property_entries(
    column: Any,
    path: str | None = None,
    conditions: Sequence[PropertyCondition] = (),
) -> Any:
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
    every depth to find it costs several times more, so the values listing,
    which names one path, follows it. Both read a group's children with
    ``_properties_in``, so they cannot disagree about where the children are.

    ``conditions`` are the filters the summary is scoped by. When walking every
    depth, a group entry that does not match the filters inside it is skipped
    along with everything in it. With a filter on ``nbi.beam.source:SW``, the
    walk skips the SS beam's entry, so the summary reports the SW beam's
    ``power`` and not the SS beam's.

    Returned as a lateral subquery, to join to the table ``column`` belongs to
    or to select from inside an EXISTS.
    """
    if path is not None:
        return _entries_at(column, path)

    by_group = _group_conditions(conditions)
    top = _properties_in(column)
    top_path = top.c.value.op("->>")("name")
    walk = (
        select(
            top_path.label("path"),
            top.c.value.label("entry"),
            top.c.value.op("->")("extent").label("extent"),
        )
        .where(_in_a_matching_instance(top_path, top.c.value, by_group))
        .cte(recursive=True, nesting=True)
    )
    children = _properties_in(walk.c.entry.op("->")("properties"))
    child_path = func.concat(
        walk.c.path, PATH_SEPARATOR, children.c.value.op("->>")("name")
    )
    walk = walk.union_all(
        select(child_path, children.c.value, walk.c.extent)
        .select_from(walk)
        .join(children, true())
        .where(_in_a_matching_instance(child_path, children.c.value, by_group))
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
