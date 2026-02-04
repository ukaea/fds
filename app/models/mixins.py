from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow():
    """
    Returns the current time in UTC, timezone-aware.
    """
    return datetime.now(timezone.utc)


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
