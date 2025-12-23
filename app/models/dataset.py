from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from .common import AccessLevel, DescriptiveMixin, TimestampMixin

if TYPE_CHECKING:
    from .shot import Shot
    from .datasetsource import DatasetSource


class DatasetBase(DescriptiveMixin, TimestampMixin, SQLModel):
    name: str = Field(index=True)
    level: int = Field(index=True)
    data_url: str
    quality_flag: str | None = Field(default=None, index=True)
    device_name: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    license: str | None = Field(default=None)
    version: str | None = Field(default=None, index=True)
    keywords: str | None = Field(default=None)  # Comma-separated list
    media_type: str | None = Field(default=None)
    format: str | None = Field(default=None)


class Dataset(DatasetBase, table=True):
    __table_args__ = (
        UniqueConstraint(
            "device_name", "shot_id", "name", name="idx_dataset_context_name"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    shot_id: str | None = Field(default=None, foreign_key="shot.id", index=True)

    shot: "Shot" = Relationship(back_populates="datasets")
    source_links: list["DatasetSource"] = Relationship(back_populates="dataset")


class DatasetCreate(DatasetBase):
    shot_id: str | None = None


class DatasetRead(DatasetBase):
    id: int
    shot_id: str | None = None
    effective_access_level: AccessLevel | None = None


class DatasetUpdate(SQLModel):
    name: str | None = None
    level: int | None = None
    data_url: str | None = None
    quality_flag: str | None = None
    device_name: str | None = None
    shot_id: str | None = None
    access_level: AccessLevel | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    license: str | None = None
    version: str | None = None
    keywords: str | None = None
    media_type: str | None = None
    format: str | None = None
