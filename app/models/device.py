from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .shot import Shot


class DeviceBase(SQLModel):
    name: str = Field(index=True)
    type: str = Field(index=True)
    began_operations: str | None = None


class Device(DeviceBase, table=True):
    id: int | None = Field(default=None, primary_key=True, index=True)
    status: str | None = Field(index=True)

    shots: list["Shot"] = Relationship(back_populates="device")


class DeviceRead(DeviceBase):
    id: int


class DeviceCreate(DeviceBase):
    status: str | None = None


class DeviceUpdate(SQLModel):
    name: str | None = None
    type: str | None = None
    began_operations: str | None = None
    status: str | None = None
