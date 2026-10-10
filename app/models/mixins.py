from datetime import date

from sqlmodel import JSON, Field, SQLModel

from app.core.timeutils import UTCDatetime, utcnow

from .scientific_metadata import ScientificProperty


class PersistentIdentifierMixin(SQLModel):
    """A globally persistent identifier registered for the record elsewhere.

    A DOI, Handle, PIDINST, ROR, ORCID or Software Heritage ID: whatever scheme
    the record's owners registered it under. FDS stores it and does not mint it.
    Either an absolute URI or a compact form such as ``doi:10.1234/abc``.
    """

    persistent_identifier: str | None = Field(default=None)


class IssuedMixin(SQLModel):
    """When the data was formally published: the date a citation gives.

    Not ``created_at``, which is when FDS listed the record.
    """

    issued: date | None = Field(default=None)


class TimestampMixin(SQLModel):
    """When FDS listed a record and last changed it, both set by FDS itself."""

    created_at: UTCDatetime = Field(
        default_factory=utcnow,
        nullable=False,
        index=True,
    )
    updated_at: UTCDatetime = Field(
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


class ScientificMetadataMixin(SQLModel):
    """Mixin adding the searchable scientific-metadata list to a model.

    Carried by the things a user searches for: a Shot, a Dataset, and a
    Collection. What the claims are *about* differs by model, but their shape,
    their projection to ``schema:additionalProperty`` and the ``property``
    filter that queries them do not, which is what makes one field serve all
    three. An Activity deliberately has no such field: it is the record of an
    event, not something discovered.
    """

    # sa_type rather than sa_column: a Column instance on a mixin is one object
    # shared by every subclass, and SQLAlchemy rejects the second table it is
    # assigned to. sa_type builds a fresh column per model.
    scientific_metadata: list[ScientificProperty] | None = Field(
        default=None, sa_type=JSON, nullable=True
    )
