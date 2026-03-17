from typing import TYPE_CHECKING

from sqlmodel import JSON, Column, Field, Relationship, SQLModel

from .mixins import DescriptiveMixin, TimestampMixin
from .policy import AccessLevel

if TYPE_CHECKING:
    from .shot import Shot
    from .source import Source


class DeviceBase(DescriptiveMixin, TimestampMixin, SQLModel):
    name: str = Field(index=True, unique=True)
    type: str | None = Field(default=None, index=True)
    began_operations: str | None = None
    status: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read resources under this device when access "
            "is restricted. If null, scope requirements are inherited by narrower "
            "contexts only when they do not define their own policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for resources under this device. If null, any "
            "globally trusted issuer is permitted unless a narrower context defines "
            "its own issuer policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )


class Device(DeviceBase, table=True):
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


class DeviceRead(DeviceBase):
    id: int
    effective_access_level: AccessLevel | None = None


class DeviceUpdate(SQLModel):
    name: str | None = None
    type: str | None = None
    began_operations: str | None = None
    status: str | None = None
    access_level: AccessLevel | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read resources under this device when access "
            "is restricted. If null, scope requirements are inherited by narrower "
            "contexts only when they do not define their own policy."
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
