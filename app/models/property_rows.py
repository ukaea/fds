from decimal import Decimal

from sqlmodel import (
    ARRAY,
    Field,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SQLModel,
)

from .mixins import JSONB_COLUMN


class PropertyRowMixin(SQLModel):
    """One property in a record's ``scientific_metadata``, at any depth.

    Derived from the JSON, which stays the record. A trigger replaces a record's
    rows whenever its metadata is written, using the SQL function
    ``scientific_properties`` defined in the migrations, so FDS never writes
    these rows itself and they can be rebuilt from the JSON at any time.

    ``path`` joins the names down to the property with ``.``, and is null only
    for a property stored without a name. ``position`` is the property's index
    in each list along the path, so the properties in one instance of a group
    share that instance's position as a prefix: ``nbi.beam.power`` at ``[3, 1,
    1]`` belongs to the beam at ``[3, 1]``. ``number`` is the value when its
    text reads as a number PostgreSQL can hold. ``dimension`` is that of the
    property's own extent, or of the outermost group it sits in.
    """

    position: tuple[int, ...] = Field(
        sa_type=ARRAY(Integer, as_tuple=True), primary_key=True
    )
    path: str | None = None
    is_group: bool
    value: str | int | float | bool | None = Field(default=None, sa_type=JSONB_COLUMN)
    number: Decimal | None = None
    unit: str | None = None
    description: str | None = None
    kind: str | None = None
    dimension: str | None = None


class ShotProperty(PropertyRowMixin, table=True):
    __table_args__ = (
        PrimaryKeyConstraint("device_name", "shot", "position"),
        ForeignKeyConstraint(
            ["device_name", "shot"],
            ["shot.device_name", "shot.id"],
            ondelete="CASCADE",
        ),
        Index("ix_shotproperty_path_number", "path", "number"),
    )
    device_name: str = Field(primary_key=True)
    shot: str = Field(primary_key=True)


class DatasetProperty(PropertyRowMixin, table=True):
    __table_args__ = (
        PrimaryKeyConstraint("dataset", "position"),
        Index("ix_datasetproperty_path_number", "path", "number"),
    )
    dataset: int = Field(foreign_key="dataset.id", primary_key=True, ondelete="CASCADE")


class CollectionProperty(PropertyRowMixin, table=True):
    __table_args__ = (
        PrimaryKeyConstraint("collection", "position"),
        Index("ix_collectionproperty_path_number", "path", "number"),
    )
    collection: int = Field(
        foreign_key="collection.id", primary_key=True, ondelete="CASCADE"
    )
