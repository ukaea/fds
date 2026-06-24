from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, PrimaryKeyConstraint, Relationship, SQLModel

from .mixins import TimestampMixin
from .policy import AccessLevel

if TYPE_CHECKING:
    from .collection import Collection
    from .dataset import Dataset
    from .device import Device, DeviceRead


class ShotBase(TimestampMixin, SQLModel):
    id: str = Field(index=True)
    shot_at: datetime | None = Field(default=None, index=True)
    shot_end: datetime | None = Field(default=None, index=True)
    shot_duration: float | None = Field(
        default=None,
        description=(
            "Shot duration in seconds. Optional. If shot_at and shot_end are both "
            "set, shot_duration must equal the interval between them."
        ),
    )
    description: str | None = Field(default=None)
    publisher: str | None = Field(default=None, index=True)
    creator: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this shot when access is restricted. "
            "If null, scope requirements inherit from the enclosing device policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this shot. If null, allowed issuers "
            "inherit from the enclosing device policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )


class Shot(ShotBase, table=True):
    __table_args__ = (PrimaryKeyConstraint("device_name", "id"),)
    id: str = Field(primary_key=True)
    device_name: str = Field(foreign_key="device.name", primary_key=True, index=True)

    device: "Device" = Relationship(
        back_populates="shots",
        sa_relationship_kwargs={
            "primaryjoin": "Shot.device_name==Device.name",
            "foreign_keys": "[Shot.device_name]",
        },
    )
    datasets: list["Dataset"] = Relationship(
        back_populates="shot",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Shot.id==Dataset.shot_id, Shot.device_name==Dataset.device_name)",
            "foreign_keys": "[Dataset.shot_id, Dataset.device_name]",
        },
    )
    collections: list["Collection"] = Relationship(
        back_populates="shot",
        sa_relationship_kwargs={
            "primaryjoin": (
                "and_(Shot.id==Collection.shot_id, "
                "Shot.device_name==Collection.device_name)"
            ),
            "foreign_keys": "[Collection.shot_id, Collection.device_name]",
        },
    )


class ShotCreate(ShotBase):
    device_name: str | None = None


class ShotRead(ShotBase):
    effective_access_level: AccessLevel | None = None
    device_name: str | None = None
    device: "DeviceRead | None" = None


class ShotUpdate(SQLModel):
    shot_at: datetime | None = None
    shot_end: datetime | None = None
    shot_duration: float | None = None
    description: str | None = None
    publisher: str | None = None
    creator: str | None = None
    access_level: AccessLevel | None = None
    device_name: str | None = None
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this shot when access is restricted. "
            "If null, scope requirements inherit from the enclosing device policy."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this shot. If null, allowed issuers "
            "inherit from the enclosing device policy."
        ),
    )
