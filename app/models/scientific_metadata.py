from enum import StrEnum
from typing import Self

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel

# Joins the names of nested properties into a path: `coolant.thermocouple.max`.
PATH_SEPARATOR = "."

# Separates a path from a value in a filter: `property=coolant.type:Water`.
PROPERTY_SEPARATOR = ":"


class MetadataKind(StrEnum):
    """What a scientific property's value *is*, as the provider intends it.

    Not how to render it: a provider should not have to know whether FDS draws
    chips or a dropdown, and an opinion about that would outlive the interface
    that prompted it. FDS chooses the control from the kind and how many
    distinct values there turn out to be.

    - ``TERM``: a value drawn from a vocabulary. Filterable by equality.
    - ``QUANTITY``: a magnitude on a scale, usually with a ``unit``. Filterable
      by range.
    - ``TEXT``: prose written for a human. Not a filter; it describes a single
      record rather than classifying it.

    Optional. When absent FDS infers the kind from the values it can see, which
    is right often enough to demand nothing of a provider, and wrong often
    enough to be worth overriding.
    """

    TERM = "term"
    QUANTITY = "quantity"
    TEXT = "text"


class Extent(SQLModel):
    """A 1D range that localises a ScientificProperty on one named axis of the data.

    ``start``/``end`` are coordinates on the axis named by ``dimension``, in that
    axis's own frame (negatives allowed). ``end = None`` marks a point (an instant
    or a single slice). Time is not special; ``dimension`` may name any axis.
    """

    dimension: str
    start: float
    end: float | None = None  # None = a point (an instant or single slice)
    unit: str | None = None  # unit of start/end on that axis


class ScientificProperty(SQLModel):
    """One claim in a record's scientific metadata.

    A property holds either a ``value`` or a list of ``properties``. One that
    holds ``properties`` is a group, such as ``coolant`` holding ``type`` and
    ``temperature_in``. A group has no value, unit or kind, because those
    describe a value; its name, description and extent describe the group.

    A value is a single scalar: text, a number, true or false, or null. Several
    values are several properties with the same name, and an object is a group.

    A group's extent covers everything inside it, so properties inside a group
    have no extent of their own. Names may not contain ``.``, which joins the
    names of nested properties into a path, or ``:``, which separates a path
    from a value in a filter.
    """

    name: str
    value: str | int | float | bool | None = None
    unit: str | None = None
    description: str | None = None
    extent: Extent | None = None  # present ⇒ an annotation: localised on one axis
    kind: MetadataKind | None = None  # absent ⇒ FDS infers it from the values
    properties: list["ScientificProperty"] | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def name_has_no_separator(cls, name: str) -> str:
        for separator in (PATH_SEPARATOR, PROPERTY_SEPARATOR):
            if separator in name:
                raise ValueError(
                    f"property name '{name}' contains '{separator}', which FDS "
                    "uses to write paths and filters; nest the property in a "
                    "group instead"
                )
        return name

    @field_validator("value", mode="before")
    @classmethod
    def value_is_a_scalar(cls, value: object) -> object:
        if isinstance(value, dict | list):
            # Pydantic turns a ValueError into a validation error; a TypeError
            # would escape it and answer the request with a server error.
            raise ValueError(  # noqa: TRY004
                "a value is text, a number, true or false, or null; write an "
                "object as a group of properties, and several values as several "
                "properties with the same name"
            )
        return value

    @model_validator(mode="after")
    def holds_a_value_or_properties(self) -> Self:
        if self.properties is None:
            # A null value is allowed, but it has to be written: a property
            # with neither a value nor properties says nothing.
            if "value" not in self.model_fields_set:
                raise ValueError(
                    f"property '{self.name}' needs a value, or properties if it "
                    "is a group"
                )
            return self

        # Checked against None rather than the fields set: a group read back
        # from the database carries "value": null, because FDS stores every
        # field of a property, set or not.
        described = [
            field
            for field in ("value", "unit", "kind")
            if getattr(self, field) is not None
        ]
        if described:
            raise ValueError(
                f"group '{self.name}' cannot have a {' or '.join(described)}: "
                "those belong on the properties inside it"
            )

        localised = [prop.name for prop in self.properties if prop.extent is not None]
        if localised:
            raise ValueError(
                f"properties inside group '{self.name}' cannot have an extent of "
                f"their own ({', '.join(localised)}); give the group the extent "
                "and it covers everything inside it"
            )
        return self
