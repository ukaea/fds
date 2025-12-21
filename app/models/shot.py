from enum import Enum
from typing import TYPE_CHECKING

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
    id: str = Field(primary_key=True, index=True)
    access_level: AccessLevel = Field(default=AccessLevel.RESTRICTED, index=True)
    device_id: int | None = Field(default=None, foreign_key="device.id", index=True)


class Shot(ShotBase, table=True):
    device: "Device" = Relationship(back_populates="shots")
    datasets: list["Dataset"] = Relationship(back_populates="shot")


class ShotCreate(SQLModel):
    id: str
    access_level: AccessLevel = AccessLevel.RESTRICTED
    device_name: str | None = None


class ShotRead(ShotBase):
    pass


class ShotUpdate(SQLModel):
    access_level: AccessLevel | None = None
    device_name: str | None = None
