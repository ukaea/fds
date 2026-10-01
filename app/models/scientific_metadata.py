from enum import StrEnum
from typing import Any

from sqlmodel import SQLModel


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
    name: str
    value: Any
    unit: str | None = None
    description: str | None = None
    extent: Extent | None = None  # present ⇒ an annotation: localised on one axis
    kind: MetadataKind | None = None  # absent ⇒ FDS infers it from the values
