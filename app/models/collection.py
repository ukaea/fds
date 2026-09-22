from typing import TYPE_CHECKING

from sqlmodel import (
    JSON,
    Column,
    Field,
    ForeignKeyConstraint,
    Relationship,
    SQLModel,
    UniqueConstraint,
)

from .mixins import DescriptiveMixin, ScientificMetadataMixin, TimestampMixin
from .policy import AccessLevel
from .scientific_metadata import ScientificProperty

if TYPE_CHECKING:
    from .activity import Activity
    from .dataset import Dataset, DatasetRead
    from .shot import Shot


class CollectionDataset(SQLModel, table=True):
    """Join table linking Collections to their member Datasets (``dcat:dataset``).

    A Dataset can belong to multiple Collections simultaneously. Rows in this
    table are inserted/deleted by ``CollectionService.add_dataset`` and
    ``CollectionService.remove_dataset``.
    """

    collection_id: int = Field(foreign_key="collection.id", primary_key=True)
    dataset_id: int = Field(foreign_key="dataset.id", primary_key=True)


class CollectionMember(SQLModel, table=True):
    """Join table recording nesting of Collections (``dcat:catalog``).

    Represents the parent → child relationship when one Collection contains
    another. Rows are inserted/deleted by ``CollectionService.add_child_collection``
    and ``CollectionService.remove_child_collection``.
    """

    parent_id: int = Field(foreign_key="collection.id", primary_key=True)
    child_id: int = Field(foreign_key="collection.id", primary_key=True)


class CollectionBase(
    DescriptiveMixin, ScientificMetadataMixin, TimestampMixin, SQLModel
):
    """Core metadata for a Collection (maps to ``dcat:Catalog``).

    A Collection is an independently citable grouping of Datasets and/or other
    Collections, optionally produced by a named ``prov:Activity``. Collections
    exist at the same scope levels as Datasets (Global, Device, Shot) and share
    the same sibling URI structure — membership is expressed in metadata, not
    URI paths.

    Fields:
        name: Stable, URL-safe identifier within its scope (device/shot).
        device_name: Device that scopes this collection. ``None`` for Global.
        access_level: Direct access policy. ``None`` means inherit from the
            enclosing Shot or device policy.
        root_url: Root access URL for all physical data in this collection.
            Format-agnostic: may be an IceChunk repository root, an FTP
            directory, an S3 prefix, or any other base location from which
            member dataset distributions are addressed. Member dataset
            ``url`` values are typically paths relative to or within this
            root. Serialised as ``dcat:accessURL`` on the collection's
            ``dcat:Distribution`` in JSON-LD. ``None`` for collections whose
            members have independent, unrelated physical locations.
        required_scopes: OAuth scopes required to read this collection when
            access is restricted. ``None`` inherits from the enclosing
            Shot/device policy.
        allowed_idps: Trusted identity-provider issuer allowlist. ``None``
            inherits from the enclosing Shot/device policy.
    """

    name: str = Field(index=True)
    device_name: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    root_url: str | None = Field(
        default=None,
        description=(
            "Root access URL for the physical data backing this collection. "
            "Format-agnostic: may be an IceChunk repo root, an FTP directory, "
            "an S3 prefix, or similar. Member dataset urls are addressed relative "
            "to or within this root. Serialised as dcat:accessURL in JSON-LD."
        ),
    )
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this collection when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this collection. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )


class Collection(CollectionBase, table=True):
    """ORM table for a Collection (``dcat:Catalog``).

    A Collection is uniquely identified within the triple (device_name, shot_id,
    name). Shot-scoped Collections carry FKs for both device_name and shot_id.
    Device-level Collections have ``shot_id=None``. Global Collections have both
    ``device_name=None`` and ``shot_id=None``.

    Dataset membership and child-Collection nesting are managed through the
    ``CollectionDataset`` and ``CollectionMember`` join tables respectively.
    The ``datasets`` relationship loads member Datasets eagerly; child
    Collections are retrieved explicitly by the service to avoid SQLModel's
    limitations with self-referential many-to-many relationships.
    """

    __table_args__ = (
        ForeignKeyConstraint(
            ["device_name", "shot_id"],
            ["shot.device_name", "shot.id"],
        ),
        UniqueConstraint(
            "device_name", "shot_id", "name", name="idx_collection_context_name"
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    shot_id: str | None = Field(default=None, index=True)
    activity_id: int | None = Field(default=None, foreign_key="activity.id", index=True)
    # The catalogue a federated record came from; NULL means it was minted in this FDS instance.
    origin: str | None = Field(default=None, index=True)

    shot: "Shot" = Relationship(
        back_populates="collections",
        sa_relationship_kwargs={
            "primaryjoin": (
                "and_(Collection.shot_id==Shot.id, "
                "Collection.device_name==Shot.device_name)"
            ),
            "foreign_keys": "[Collection.shot_id, Collection.device_name]",
        },
    )
    activity: "Activity" = Relationship(back_populates="collections")
    # Member Datasets — managed via CollectionDataset join table.
    datasets: list["Dataset"] = Relationship(link_model=CollectionDataset)
    # Child Collections are NOT declared as a SQLModel Relationship here because
    # SQLModel cannot automatically resolve self-referential M2M join columns.
    # Use CollectionService._get_child_collections() instead.


class CollectionCreate(CollectionBase):
    """Schema for creating a Collection.

    ``shot_id`` and ``activity_id`` are optional. A Collection can exist at
    Global, Device, or Shot scope, and does not require a provenance activity.
    """

    shot_id: str | None = None
    activity_id: int | None = None
    origin: str | None = None


class CollectionRead(CollectionBase):
    """Collection response schema.

    Member Datasets are inlined as ``DatasetRead`` objects. Child Collections
    are inlined one level deep as ``CollectionRead`` objects; their own
    ``datasets`` and ``child_collections`` fields are omitted to prevent
    unbounded recursive nesting in the response.
    """

    id: int
    shot_id: str | None = None
    activity_id: int | None = None
    origin: str | None = None
    effective_access_level: AccessLevel | None = None
    datasets: list["DatasetRead"] | None = None
    child_collections: list["CollectionRead"] | None = None


class CollectionUpdate(SQLModel):
    """Schema for partial updates to a Collection.

    All fields are optional. Context fields (``device_name``, ``shot_id``)
    cannot be used to move a Collection between scopes — the service will
    reject any attempt to change them.
    """

    name: str | None = None
    device_name: str | None = None
    shot_id: str | None = None
    activity_id: int | None = None
    access_level: AccessLevel | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    scientific_metadata: list[ScientificProperty] | None = None
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this collection when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this collection. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
    )
