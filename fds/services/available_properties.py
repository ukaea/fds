from collections.abc import Sequence

from sqlalchemy import ColumnElement
from sqlmodel import (
    Session,
    SQLModel,
    col,
    distinct,
    func,
    select,
)

from fds.models.available_properties import AvailableProperties, AvailableProperty
from fds.models.scientific_metadata import MetadataKind
from fds.services.exceptions import FDSValidationError
from fds.services.filters import (
    PropertyCondition,
    in_matching_instances,
    property_rows,
    record_columns,
    value_text,
)

# A name with thousands of values is not something to pick from a list, so
# enumeration is capped rather than paged: past this many distinct values a
# caller filters some other way. The ceiling bounds the response, not the scan,
# which costs the same either way.
DEFAULT_MAX_VALUES = 20
MAX_VALUES_LIMIT = 200

# Above this share of distinct-values-per-record a name is prose, not a
# vocabulary: its values are written for one record rather than classifying it.
# `objective` has 100-character values but repeats each ~12 times, so it is a
# vocabulary; `postshot_comment` is near-unique per shot, so it is not. Length
# misfiles the first; this does not.
PROSE_RATIO = 0.5

# Below this many records the ratio is noise, because three records with three
# values look exactly like prose, so cardinality alone decides.
RATIO_FLOOR = 20


def infer_kind(distinct_values: int, records: int, numeric: bool) -> MetadataKind:
    """Guess what a property is from the values in scope, when nobody has said.

    Cardinality is read before type, and the order matters. Type first calls
    anything numeric a quantity, which is right for a measured current and wrong
    for a target current range: three options, stored as numbers because that is
    the correct way to store them. A handful of repeated values is a vocabulary
    whether or not those values are numbers.

    ``records`` guards the ratio rather than the count: on a twenty-shot device
    a measurement has twenty distinct values, under any sane cap, and only the
    fact that they never repeat tells them apart from a vocabulary.
    """
    repeats = records >= RATIO_FLOOR and distinct_values / records < PROSE_RATIO
    small = 0 < distinct_values <= MAX_VALUES_LIMIT

    if small and (repeats or records < RATIO_FLOOR):
        return MetadataKind.TERM
    if numeric:
        return MetadataKind.QUANTITY
    return MetadataKind.TERM if repeats else MetadataKind.TEXT


def available_properties(
    session: Session,
    model: type[SQLModel],
    *,
    where: Sequence[ColumnElement[bool]] = (),
    conditions: Sequence[PropertyCondition] = (),
    max_values: int = DEFAULT_MAX_VALUES,
    include_constant: bool = False,
) -> AvailableProperties:
    """Summarise the scientific metadata carried by the records ``where`` selects.

    Knows nothing about who is asking. The caller supplies every restriction,
    including the one limiting the scope to records the user may read, which is
    what lets this serve Shot and Dataset alike.

    Aggregates rather than listings: a device's shots hold tens of thousands of
    distinct values between them and none of them need to leave the database to
    be counted.

    ``conditions`` are the parsed property filters that ``where`` was built
    from. They decide which group entries are summarised: with a filter on
    ``nbi.beam.source:SW``, the values reported for ``nbi.beam.power`` are the
    SW beam's alone, not those of every beam on the same shot.

    A property is left out when every record in scope has the same single value
    for it, because picking that value would not narrow anything.
    ``include_constant`` lists it anyway, for a filter panel working out which
    options are still possible once something has been picked.
    """
    if not 0 <= max_values <= MAX_VALUES_LIMIT:
        raise FDSValidationError(
            f"max_values must be between 0 and {MAX_VALUES_LIMIT}, got {max_values}."
        )

    total = session.exec(select(func.count()).select_from(model).where(*where)).one()

    rows, of_record = property_rows(model)
    # Counting records, not entries: one shot annotated twice under the same
    # name is one record. Counting each record's first row under a path is much
    # quicker than counting DISTINCT over Shot's composite key, which compares
    # row values.
    first = func.row_number().over(partition_by=[col(rows.path), *record_columns(rows)])
    looked_at = (
        select(rows, (first == 1).label("first"))
        .select_from(model)
        .join(rows, of_record)
        .where(
            *where,
            ~col(rows.is_group),
            *in_matching_instances(rows, conditions),
        )
        .subquery()
    )
    value = value_text(looked_at.c.value)
    number = looked_at.c.number

    # Everything else travels in one json_build_object, to stay inside the four
    # typed entities sqlmodel.select() has overloads for. The counts alongside
    # each value are what let the caller tell "they all agree" from "one of
    # several": a name recorded in both A and kA has no single unit, and saying
    # nothing beats saying one of them.

    summary = session.exec(
        select(
            looked_at.c.path.label("name"),
            func.count().filter(looked_at.c.first).label("records"),
            func.count(distinct(value)).label("distinct"),
            func.json_build_object(
                "unit",
                func.max(looked_at.c.unit),
                "units",
                func.count(distinct(looked_at.c.unit)),
                "description",
                func.max(looked_at.c.description),
                "descriptions",
                func.count(distinct(looked_at.c.description)),
                "kind",
                func.max(looked_at.c.kind),
                "kinds",
                func.count(distinct(looked_at.c.kind)),
                "dimension",
                func.max(looked_at.c.dimension),
                "numeric",
                func.bool_and(number.is_not(None)).filter(value.is_not(None)),
                "min",
                func.min(number),
                "max",
                func.max(number),
            ).label("extra"),
        ).group_by(looked_at.c.path)
    ).all()

    properties: list[AvailableProperty] = []
    for row_name, records, distinct_values, extra in summary:
        if row_name is None:
            continue
        # A provider that disagrees with itself about a name's kind is not
        # declaring anything, so fall back to inference rather than pick one.
        kind = (
            MetadataKind(extra["kind"])
            if extra["kinds"] == 1 and extra["kind"] in set(MetadataKind)
            else infer_kind(distinct_values, records, bool(extra["numeric"]))
        )
        if kind is MetadataKind.TEXT:
            # Prose describes one record; it does not classify it. Offering it
            # as a filter is what made the panel a dumping ground.
            continue
        if distinct_values <= 1 and records == total and not include_constant:
            # One value, on every record in scope: selecting it returns the
            # scope unchanged. A filter that cannot divide anything is not a
            # filter, whatever it says about the data.
            continue
        properties.append(
            AvailableProperty(
                name=row_name,
                records=records,
                distinct=distinct_values,
                kind=kind,
                unit=extra["unit"] if extra["units"] == 1 else None,
                description=(
                    extra["description"] if extra["descriptions"] == 1 else None
                ),
                dimension=extra["dimension"],
                min=float(extra["min"]) if extra["min"] is not None else None,
                max=float(extra["max"]) if extra["max"] is not None else None,
            )
        )

    _attach_values(session, model, where, conditions, properties, max_values)

    # Annotations first: they carry a where, and they are the ones that grow. Then
    # terms before quantities, and within each the short rows lead, so the order
    # does not shift as the catalogue grows.
    order = {MetadataKind.TERM: 0, MetadataKind.QUANTITY: 1, MetadataKind.TEXT: 2}
    properties.sort(
        key=lambda f: (
            f.dimension is None,
            order[f.kind],
            f.values is None,
            f.distinct,
            f.name,
        )
    )
    return AvailableProperties(total=total, properties=properties)


def _attach_values(
    session: Session,
    model: type[SQLModel],
    where: Sequence[ColumnElement[bool]],
    conditions: Sequence[PropertyCondition],
    properties: list[AvailableProperty],
    max_values: int,
) -> None:
    """Fill in the values of every term prop small enough to enumerate."""
    enumerable = [
        f.name
        for f in properties
        if f.kind is MetadataKind.TERM and 0 < f.distinct <= max_values
    ]
    if not enumerable or max_values == 0:
        return

    rows, of_record = property_rows(model)
    value = value_text(col(rows.value))
    found: dict[str | None, list[str]] = {name: [] for name in enumerable}
    for row_name, row_value in session.exec(
        select(col(rows.path), value)
        .select_from(model)
        .join(rows, of_record)
        .where(
            *where,
            col(rows.path).in_(enumerable),
            value.is_not(None),
            *in_matching_instances(rows, conditions),
        )
        .distinct()
    ).all():
        found[row_name].append(row_value)

    for prop in properties:
        if prop.name in found:
            prop.values = _sorted_values(found[prop.name])


def _sorted_values(values: list[str]) -> list[str]:
    """Numerically when the values are numbers, alphabetically otherwise.

    A target current range stored as 400, 700 and 1000 reads in that order; as
    text it reads 1000, 400, 700. Sorted here rather than in SQL so the order
    does not depend on the database's collation.
    """
    try:
        return sorted(values, key=float)
    except ValueError:
        return sorted(values)
