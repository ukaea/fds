from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel

from .common import AccessLevel, DescriptiveMixin, TimestampMixin

if TYPE_CHECKING:
    from .dataset import Dataset
    from .device import Device, DeviceRead


class ShotBase(DescriptiveMixin, TimestampMixin, SQLModel):
    id: str = Field(primary_key=True, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    device_id: int | None = Field(default=None, foreign_key="device.id", index=True)


class Shot(ShotBase, table=True):
    device: "Device" = Relationship(back_populates="shots")
    datasets: list["Dataset"] = Relationship(back_populates="shot")

    @property
    def device_name(self) -> str | None:
        """
        Calculated property that provides the device name from the relationship,
        avoiding the need for the client to handle internal integer IDs.
        """
        return self.device.name if self.device else None


class ShotCreate(SQLModel):
    id: str
    access_level: AccessLevel | None = None
    device_name: str | None = None


class ShotRead(SQLModel):
    id: str
    access_level: AccessLevel | None = None
    effective_access_level: AccessLevel | None = None
    device_name: str | None = None
    device: "DeviceRead | None" = None


class ShotUpdate(SQLModel):
    access_level: AccessLevel | None = None
    device_name: str | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
