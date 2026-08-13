from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .activity import Activity
    from .device import Device


class SourceKind(str, Enum):
    """How a Source projects into the PROV-O graph. Required.

    A ``Source`` is a registry of producers/tools, not a single PROV class:
    - ``software``: an analysis code, scheduler, or DAQ → ``prov:SoftwareAgent``.
    - ``instrument``: a diagnostic device → ``prov:Entity``, entering activities
      via ``prov:used`` with ``prov:hadRole = instrument`` (it has no agency).
    - ``person``: an individual → ``prov:Person``.
    - ``organization``: a group or facility → ``prov:Organization``.
    """

    SOFTWARE = "software"
    INSTRUMENT = "instrument"
    PERSON = "person"
    ORGANIZATION = "organization"


class SourceBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str | None = None
    kind: SourceKind = Field(index=True)


class Source(SourceBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    device_id: int | None = Field(default=None, foreign_key="device.id", nullable=True)

    device: "Device" = Relationship(back_populates="sources")
    activities: list["Activity"] = Relationship(back_populates="source")


class SourceRead(SourceBase):
    id: int
    device_name: str | None = None


class SourceCreate(SourceBase):
    device_name: str | None = None


class SourceUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    kind: SourceKind | None = None
