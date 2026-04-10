from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .dataset import Dataset
    from .source import Source


class ActivityInput(SQLModel, table=True):
    """Join table recording datasets consumed as inputs by an Activity (prov:used)."""

    activity_id: int = Field(foreign_key="activity.id", primary_key=True)
    dataset_id: int = Field(foreign_key="dataset.id", primary_key=True)


class ActivityBase(SQLModel):
    source_id: int = Field(foreign_key="source.id")
    source_version: str | None = None
    activity_type: str | None = None  # e.g. "SIMULATION", "MEASUREMENT"
    parameters: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Activity(ActivityBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    source: "Source" = Relationship(back_populates="activities")
    datasets: list["Dataset"] = Relationship(back_populates="activity")
    input_datasets: list["Dataset"] = Relationship(link_model=ActivityInput)


class ActivityCreate(ActivityBase):
    pass


class ActivityRead(ActivityBase):
    id: int


class ActivityUpdate(SQLModel):
    source_id: int | None = None
    source_version: str | None = None
    activity_type: str | None = None
    parameters: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime | None = None
    ended_at: datetime | None = None
