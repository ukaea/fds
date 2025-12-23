from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

from .common import AccessLevel, DescriptiveMixin, TimestampMixin


if TYPE_CHECKING:
    from .shot import Shot


class DeviceBase(DescriptiveMixin, TimestampMixin, SQLModel):
    name: str = Field(index=True, unique=True)
    type: str | None = Field(default=None, index=True)
    began_operations: str | None = None
    status: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)


class Device(DeviceBase, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    shots: list["Shot"] = Relationship(back_populates="device")


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
