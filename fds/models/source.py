from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Column, Field, Relationship, SQLModel

from .mixins import JSONB_COLUMN, PersistentIdentifierMixin
from .policy import AccessLevel

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


READ_ROLES = (
    "Roles that may read this source if it is restricted. Holding any one is "
    "enough; an empty list lets in anyone signed in. If null, the linked "
    "device's list applies."
)
WRITE_ROLES = (
    "Roles that may change or delete this source. Holding any one is enough. "
    "Only fds-admin may set it. If null, the linked device's list applies."
)
ALLOWED_IDPS = (
    "Trusted issuer allowlist for this source. If null, the linked device's "
    "list applies."
)


class SourceBase(PersistentIdentifierMixin, SQLModel):
    name: str = Field(index=True, unique=True)
    description: str | None = None
    kind: SourceKind = Field(index=True)
    access_level: AccessLevel | None = Field(
        default=None,
        index=True,
        description=(
            "public, embargoed or restricted. A source has no data to hold back, "
            "so embargoed reads as public. If null, the linked device's level "
            "applies, and a source linked to no device is restricted."
        ),
    )
    read_roles: list[str] | None = Field(
        default=None,
        description=READ_ROLES,
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )
    write_roles: list[str] | None = Field(
        default=None,
        description=WRITE_ROLES,
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=ALLOWED_IDPS,
        sa_column=Column(JSONB_COLUMN, nullable=True),
    )


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
    persistent_identifier: str | None = None
    description: str | None = None
    kind: SourceKind | None = None
    access_level: AccessLevel | None = None
    read_roles: list[str] | None = Field(default=None, description=READ_ROLES)
    write_roles: list[str] | None = Field(default=None, description=WRITE_ROLES)
    allowed_idps: list[str] | None = Field(default=None, description=ALLOWED_IDPS)
