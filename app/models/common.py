from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def utcnow():
    """
    Returns the current time in UTC, timezone-aware.
    """
    return datetime.now(timezone.utc)


class AccessLevel(str, Enum):
    """
    Enum for the access level of an entity.
    - PUBLIC: Accessible to anyone.
    - RESTRICTED: Accessible to authenticated users with general permissions.
    - EMBARGOED: Accessible only to a specific list of users.
    """

    PUBLIC = "public"
    RESTRICTED = "restricted"
    EMBARGOED = "embargoed"


class TimestampMixin(SQLModel):
    """
    Mixin to add creation and update timestamps to a model.
    """

    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        index=True,
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        index=True,
        sa_column_kwargs={"onupdate": utcnow},
    )


class DescriptiveMixin(SQLModel):
    """
    Mixin to add DCAT/DCT standard descriptive metadata to a model.
    """

    title: str | None = Field(default=None, index=True)
    description: str | None = Field(default=None)
    publisher: str | None = Field(default=None, index=True)
