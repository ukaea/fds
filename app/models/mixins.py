from datetime import datetime

from sqlmodel import Field, SQLModel

from app.core.timeutils import utcnow


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
    creator: str | None = Field(default=None, index=True)
