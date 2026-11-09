import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased
from sqlmodel import (
    SQLModel,
    Text,
    and_,
    cast,
    col,
    exists,
    literal,
    literal_column,
    or_,
    select,
    true,
)

from app.models.activity import Activity, ActivityType
from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.policy import AccessLevel
from app.models.property_rows import (
    CollectionProperty,
    DatasetProperty,
    PropertyRowMixin,
    ShotProperty,
)
from app.models.scientific_metadata import PATH_SEPARATOR, PROPERTY_SEPARATOR
from app.models.scope import CatalogueScope, DeviceScope
from app.models.shot import Shot
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
    """The stored JSON values a query-string value matches, as JSON text.

    Query parameters are always strings, but a stored property value keeps its
    JSON type, so ``?property=disruption:true`` must still match a stored
    ``true``. Rather than guess the provider's intended type, the value matches
    as a string *or* as the boolean or number it spells. Numbers compare as
    numbers, so ``1e-05``, ``0.00001`` and ``1.0e-5`` are one value, and ``12``
    matches a stored ``12.0``.
    """
    candidates = [json.dumps(value)]
    if value.lower() in ("true", "false"):
        candidates.append(value.lower())
    elif (number := _json_number(value)) is not None:
        candidates.append(number)
    return candidates


# Matches a number written in decimal or scientific notation. The SQL function
# that fills the property tables holds a copy, to read stored values with.
NUMERIC_TEXT = r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$"

# The most digits PostgreSQL's numeric holds before and after the decimal point.
NUMERIC_DIGITS_BEFORE_POINT = 131072
NUMERIC_DIGITS_AFTER_POINT = 16383


def _json_number(value: str) -> str | None:
    """``value`` as a JSON number, when it spells one PostgreSQL can hold.

    Written through Decimal, which keeps every digit and drops the leading
    zeros JSON forbids. A number past PostgreSQL's limits would fail the whole
    query, and no stored number can be one, so it is left out.
    """
    if not re.fullmatch(NUMERIC_TEXT, value):
        return None
    number = Decimal(value)
    before_point = number.adjusted() + 1
    after_point = -int(number.as_tuple().exponent)
    if (
        before_point > NUMERIC_DIGITS_BEFORE_POINT
        or after_point > NUMERIC_DIGITS_AFTER_POINT
    ):
        return None
    return str(number)


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


PROPERTY_ROWS: dict[type[SQLModel], type[PropertyRowMixin]] = {
    Shot: ShotProperty,
    Dataset: DatasetProperty,
    Collection: CollectionProperty,
}


def _record_key(rows: type[PropertyRowMixin]) -> list[tuple[str, str]]:
    """Each column of ``rows`` naming its record, with the record's column it holds."""
    (constraint,) = rows.__table__.foreign_key_constraints  # type: ignore[attr-defined]
    return [(key.parent.name, key.column.name) for key in constraint.elements]


def property_rows(
    model: type[SQLModel],
) -> tuple[type[PropertyRowMixin], ColumnElement[bool]]:
    """The table of the properties of ``model``'s records, and the clause joining
    a row of it to its record."""
    rows = PROPERTY_ROWS[model]
    return rows, and_(
        *(
            getattr(rows, ours) == getattr(model, theirs)
            for ours, theirs in _record_key(rows)
        )
    )


def record_columns(rows: Any) -> list[Any]:
    """The columns of a property row that name its record."""
    return [getattr(rows, ours) for ours, _ in _record_key(rows)]


def value_text(value: Any) -> ColumnElement[str]:
    """A property's JSON value as text: a string without its quotes, a number
    or boolean as written, and nothing for no value."""
    return value.op("#>>", return_type=Text)(literal_column("'{}'"))


@dataclass(frozen=True)
class _Within:
    """Where the properties that conditions name are looked for.

    In one record, whose key ``record`` gives as columns of the query around
    the conditions, or in one instance of a group in it: ``group`` is the
    group's path and ``position`` the instance's position.
    """

    rows: type[PropertyRowMixin]
    record: tuple[Any, ...]
    group: str | None = None
    position: Any = None

    def path(self, name: str) -> str:
        return name if self.group is None else f"{self.group}{PATH_SEPARATOR}{name}"

    def properties(self, name: str) -> tuple[Any, list[ColumnElement[bool]]]:
        """A fresh alias of the rows, and the clauses keeping the properties
        named ``name`` here."""
        row = aliased(self.rows)
        clauses = [
            getattr(row, ours) == key
            for (ours, _), key in zip(_record_key(self.rows), self.record, strict=True)
        ]
        clauses.append(col(row.path) == self.path(name))
        if self.group is not None:
            depth = self.group.count(PATH_SEPARATOR) + 1
            clauses.append(col(row.position)[1:depth] == self.position)
        return row, clauses

    def inside(self, instance: Any, name: str) -> "_Within":
        """Within ``instance``, a row of the group named ``name`` here.

        The record is named by ``instance``'s own columns: SQLAlchemy
        correlates a subquery only with the query directly around it.
        """
        return _Within(
            self.rows,
            tuple(record_columns(instance)),
            self.path(name),
            col(instance.position),
        )


def _meets(condition: PropertyCondition, row: Any) -> ColumnElement[bool]:
    """Whether the property ``row`` meets ``condition``, its path aside."""
    if condition.bound is not None:
        number = col(row.number)
        return (
            number >= condition.bound if condition.lower else number <= condition.bound
        )
    if condition.value is None:
        return true()
    return or_(
        *(
            col(row.value) == cast(literal(candidate), JSONB)
            for candidate in _value_candidates(condition.value)
        )
    )


def _clauses_within(
    within: _Within, conditions: Sequence[PropertyCondition]
) -> list[ColumnElement[bool]]:
    """The clauses the properties ``within`` must meet for ``conditions``.

    A condition on a property here is met by any property at its path.
    Presence and values of one path are alternatives and OR together, and each
    bound is a clause of its own. The conditions on properties inside a group
    must all be met in one instance of it, so they go in a single EXISTS over
    the group's instances, built the same way one level down.
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
            row, at = within.properties(name)
            clauses.append(
                exists().where(*at, or_(*(_meets(c, row) for c in alternatives)))
            )
        for bound in (c for c in named_here if c.bound is not None):
            row, at = within.properties(name)
            clauses.append(exists().where(*at, _meets(bound, row)))
    for name, named_inside in inside.items():
        instance, at = within.properties(name)
        inner = [replace(c, names=c.names[1:]) for c in named_inside]
        clauses.append(
            exists().where(*at, *_clauses_within(within.inside(instance, name), inner))
        )
    return clauses


def property_clauses(
    model: type[SQLModel],
    properties: list[str] | None,
    minimums: list[str] | None = None,
    maximums: list[str] | None = None,
) -> list[ColumnElement[bool]]:
    """Parse and build the clauses for the ``property`` filters on ``model``.

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
    rows = PROPERTY_ROWS[model]
    record = tuple(getattr(model, theirs) for _, theirs in _record_key(rows))
    return _clauses_within(
        _Within(rows, record), property_conditions(properties, minimums, maximums)
    )


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


def in_matching_instances(
    rows: type[PropertyRowMixin], conditions: Sequence[PropertyCondition]
) -> list[ColumnElement[bool]]:
    """Whether the summary should look at a row of ``rows``, given the filters.

    A property inside a group is looked at only if the instance of the group it
    sits in matches the filters that apply inside that group, at every level.
    With a filter on ``nbi.beam.source:SW``, the SS beam's ``power`` is
    skipped. Every property outside a filtered group is looked at.
    """
    record = tuple(record_columns(rows))
    clauses: list[ColumnElement[bool]] = []
    for group, inner in _group_conditions(conditions).items():
        depth = group.count(PATH_SEPARATOR) + 1
        instance = _Within(rows, record, group, col(rows.position)[1:depth])
        clauses.append(
            or_(
                ~col(rows.path).startswith(f"{group}{PATH_SEPARATOR}", autoescape=True),
                and_(*_clauses_within(instance, inner)),
            )
        )
    return clauses


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
    """
    return and_(
        *(
            column.is_(None) if value is None else column == value
            for column, value in (
                (access_level_column, access_level),
                (scopes_column, required_scopes),
                (idps_column, allowed_idps),
            )
        )
    )


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
