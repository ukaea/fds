from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, PrimaryKeyConstraint, Relationship, SQLModel

from .mixins import DescriptiveMixin, TimestampMixin
from .policy import AccessLevel

if TYPE_CHECKING:
    from .collection import Collection
    from .dataset import Dataset
    from .device import Device, DeviceRead


class ShotBase(DescriptiveMixin, TimestampMixin, SQLModel):
    id: str = Field(index=True)
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


class ShotCreate(SQLModel):
    id: str
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


class ShotRead(SQLModel):
    id: str
    access_level: AccessLevel | None = None
    effective_access_level: AccessLevel | None = None
    device_name: str | None = None
    device: "DeviceRead | None" = None
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes defined directly on this shot. Null means scope policy is "
            "inherited from a broader context."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuers defined directly on this shot. Null means issuer policy "
            "is inherited from a broader context."
        ),
    )


class ShotUpdate(SQLModel):
    access_level: AccessLevel | None = None
    device_name: str | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
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
