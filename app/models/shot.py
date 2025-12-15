from typing import TYPE_CHECKING
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .device import Device
    from .dataset import Dataset


class AccessLevel(str, Enum):
    """
    Enum for the access level of a shot.
    - PUBLIC: Accessible to anyone.
    - RESTRICTED: Accessible to authenticated users with general permissions.
    - EMBARGOED: Accessible only to a specific list of users.
    """
    PUBLIC = "public"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"


class ShotBase(SQLModel):
    shot_number: int = Field(index=True)
    device_id: int = Field(foreign_key="device.id")
    access_level: AccessLevel = Field(default=AccessLevel.RESTRICTED, index=True)


class Shot(ShotBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    device: "Device" = Relationship(back_populates="shots")
    datasets: list["Dataset"] = Relationship(back_populates="shot")


class ShotRead(ShotBase):
    id: int


class ShotUpdate(SQLModel):
    shot_number: int | None = None
    access_level: AccessLevel | None = None


class ShotCreate(ShotBase):
    pass
