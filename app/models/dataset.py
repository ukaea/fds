from typing import TYPE_CHECKING

from sqlmodel import (
    JSON,
    Column,
    Field,
    ForeignKeyConstraint,
    Relationship,
    SQLModel,
    UniqueConstraint,
)

from .mixins import DescriptiveMixin, TimestampMixin
from .policy import AccessLevel

if TYPE_CHECKING:
    from .datasetsource import DatasetSource
    from .shot import Shot


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
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this dataset when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this dataset. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )


class Dataset(DatasetBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["device_name", "shot_id"],
            ["shot.device_name", "shot.id"],
        ),
        UniqueConstraint(
            "device_name", "shot_id", "name", name="idx_dataset_context_name"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    shot_id: str | None = Field(default=None, index=True)

    shot: "Shot" = Relationship(
        back_populates="datasets",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Dataset.shot_id==Shot.id, Dataset.device_name==Shot.device_name)",
            "foreign_keys": "[Dataset.shot_id, Dataset.device_name]",
        },
    )
    source_links: list["DatasetSource"] = Relationship(back_populates="dataset")


class DatasetCreate(DatasetBase):
    shot_id: str | None = None


class DatasetRead(DatasetBase):
    id: int
    shot_id: str | None = None
    effective_access_level: AccessLevel | None = None
    storage_options: dict[str, str | dict] | None = None


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
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this dataset when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this dataset. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
    )
