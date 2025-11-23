from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .device import Device
    from .shotsource import ShotSource


class ShotBase(SQLModel):
    shot_number: int = Field(index=True)
    device_id: int = Field(foreign_key="device.id")


class Shot(ShotBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    device: "Device | None" = Relationship(back_populates="shots")
    source_links: list["ShotSource"] = Relationship(back_populates="shot")


class ShotRead(ShotBase):
    id: int



class ShotCreate(ShotBase):
    pass
