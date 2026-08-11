from typing import Any

from sqlmodel import SQLModel


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
    extent: Extent | None = None  # present ⇒ a feature localised on one axis
