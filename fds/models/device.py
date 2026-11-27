from typing import TYPE_CHECKING

from sqlmodel import Column, Field, Relationship, SQLModel

from .mixins import (
    JSONB_COLUMN,
    DescriptiveMixin,
    PersistentIdentifierMixin,
    TimestampMixin,
)
from .policy import AccessLevel

if TYPE_CHECKING:
    from .shot import Shot
    from .source import Source


class DeviceBase(DescriptiveMixin, PersistentIdentifierMixin, SQLModel):
    name: str = Field(index=True, unique=True)
    type: str | None = Field(default=None, index=True)
    began_operations: str | None = None
    status: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    read_roles: list[str] | None = Field(
        default=None,
        description=(
            "Roles that may read this device's restricted records and get credentials "
            "for their embargoed and restricted data. Holding any one is enough; an "
            "empty list lets in anyone signed in. Records under the device that set no "
            "list of their own use this one."
        ),
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )
    write_roles: list[str] | None = Field(
        default=None,
        description=(
            "Roles that may change or delete this device and create, change and delete "
            "the records under it. Holding any one is enough. Only fds-admin may set it. "
            "Records under the device that set no list of their own use this one."
        ),
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for resources under this device. If null, any "
            "globally trusted issuer is permitted unless a narrower context defines "
            "its own issuer policy."
        ),
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )


class Device(DeviceBase, TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    shots: list["Shot"] = Relationship(
        back_populates="device",
        sa_relationship_kwargs={
            "primaryjoin": "Device.name==Shot.device_name",
            "foreign_keys": "[Shot.device_name]",
        },
    )
    sources: list["Source"] = Relationship(back_populates="device")


class DeviceCreate(DeviceBase):
    pass


class DeviceRead(DeviceBase, TimestampMixin):
    id: int
    effective_access_level: AccessLevel | None = None


class DeviceUpdate(SQLModel):
    name: str | None = None
    persistent_identifier: str | None = None
    type: str | None = None
    began_operations: str | None = None
    status: str | None = None
    access_level: AccessLevel | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    read_roles: list[str] | None = Field(
        default=None,
        description=(
            "Roles that may read this device's restricted records and get credentials "
            "for their embargoed and restricted data. Holding any one is enough; an "
            "empty list lets in anyone signed in. Records under the device that set no "
            "list of their own use this one."
        ),
    )
    write_roles: list[str] | None = Field(
        default=None,
        description=(
            "Roles that may change or delete this device and create, change and delete "
            "the records under it. Holding any one is enough. Only fds-admin may set it. "
            "Records under the device that set no list of their own use this one."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for resources under this device. If null, any "
            "globally trusted issuer is permitted unless a narrower context defines "
            "its own issuer policy."
        ),
    )
