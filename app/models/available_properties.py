from sqlmodel import SQLModel

from app.models.scientific_metadata import MetadataKind


class AvailableProperty(SQLModel):
    """One scientific-metadata name in scope, and what can be said about it.

    ``kind`` is the provider's declaration where there is one and FDS's
    inference otherwise. It says what the values *are*, and the client chooses a
    control from it together with ``distinct``: a term with three values is a
    set of chips, a term with nine hundred is something you search.

    ``values`` is present only when there are few enough to enumerate.
    ``distinct`` is always present, so an absent ``values`` means "too many to
    list" rather than "none".

    ``unit`` is reported only when every record in scope agrees on one, because
    a name recorded in both A and kA has no single unit. ``description`` follows
    the same rule, so the meaning of a name can sit beside its filter.
    ``min``/``max`` are set for quantities. ``dimension`` is set when the
    property carries an extent,
    marking it an annotation: a statement about a region of the data rather than
    about the record as a whole.
    """

    name: str
    records: int
    distinct: int
    kind: MetadataKind
    unit: str | None = None
    description: str | None = None
    dimension: str | None = None
    min: float | None = None
    max: float | None = None
    values: list[str] | None = None


class PropertyValue(SQLModel):
    """One value of a name, and how many records in scope carry it."""

    value: str
    records: int


class PropertyValues(SQLModel):
    """A page of a name's values, for a vocabulary too large to enumerate."""

    name: str
    distinct: int
    values: list[PropertyValue] = []


class AvailableProperties(SQLModel):
    """The scientific metadata available in one scope, and the size of that scope.

    ``total`` counts the records the caller may read, after any filter, which is
    what makes it a denominator a listing page cannot give.
    """

    total: int
    properties: list[AvailableProperty] = []
