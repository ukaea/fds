from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .dataset import Dataset
    from .source import Source


class DatasetSourceBase(SQLModel):
    dataset_id: int
    source_id: int
    source_version: str | None = None
    activity_type: str | None = None  # e.g., "SIMULATION", "MEASUREMENT"
    parameters: dict | None = Field(default=None, sa_column=Column(JSON))


class DatasetSource(DatasetSourceBase, table=True):
    dataset_id: int | None = Field(
        default=None, foreign_key="dataset.id", primary_key=True
    )
    source_id: int | None = Field(
        default=None, foreign_key="source.id", primary_key=True
    )

    dataset: "Dataset" = Relationship(back_populates="source_links")
    source: "Source" = Relationship(back_populates="dataset_links")


class DatasetSourceLink(SQLModel):
    dataset_id: int | None = None
    source_id: int
    source_version: str | None = None
    activity_type: str | None = None
    parameters: dict | None = Field(default=None, sa_column=Column(JSON))


class DatasetSourceRead(DatasetSourceBase):
    pass
