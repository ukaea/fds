from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .shot import Shot
    from .datasetsource import DatasetSource


class DatasetBase(SQLModel):
    name: str = Field(index=True)
    level: int = Field(index=True)
    data_url: str
    quality_flag: str | None = Field(default=None, index=True)


class Dataset(DatasetBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    shot_id: int = Field(foreign_key="shot.id")

    shot: "Shot" = Relationship(back_populates="datasets")
    source_links: list["DatasetSource"] = Relationship(back_populates="dataset")


class DatasetCreate(DatasetBase):
    shot_id: int


class DatasetRead(DatasetBase):
    id: int
    shot_id: int


class DatasetUpdate(SQLModel):
    name: str | None = None
    level: int | None = None
    data_url: str | None = None
    quality_flag: str | None = None
