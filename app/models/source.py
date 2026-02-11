from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .datasetsource import DatasetSource
    from .device import Device


class SourceBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str | None = None


class Source(SourceBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_id: int | None = Field(default=None, foreign_key="device.id", nullable=True)

    device: "Device" = Relationship(back_populates="sources")
    dataset_links: list["DatasetSource"] = Relationship(back_populates="source")


class SourceRead(SourceBase):
    id: int
    device_id: int | None = None


class SourceCreate(SourceBase):
    device_name: str | None = None


class SourceUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
