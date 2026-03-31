from typing import TYPE_CHECKING, Any

from sqlmodel import Field, Relationship, SQLModel

from .policy import AccessLevel

if TYPE_CHECKING:
    from .dataset import Dataset


class DistributionBase(SQLModel):
    """A physical access path for a Dataset (maps to ``dcat:Distribution``).

    All distributions of the same dataset must be scientifically interchangeable:
    they represent the same data in different serialisations or behind different
    access controls.  Quantitatively different data belongs in a separate Dataset.

    Fields:
        url: The download or access URL for this distribution
            (``dcat:downloadURL``).
        media_type: IANA media type / MIME type of the file, e.g.
            ``application/x-hdf5`` or ``text/csv``  (``dcat:mediaType``).
            Use this when you need machine-readable type identification — it
            must be a registered IANA media type string.
        format: Human-readable or controlled-vocabulary format label, e.g.
            ``"HDF5"``, ``"NetCDF-4"``, ``"CSV"``  (``dct:format``).
            Use this for display and discovery; it is not required to be an
            IANA media type.  Both fields may be populated simultaneously —
            ``media_type`` for interoperability, ``format`` for readability.
        access_level: Override access policy for this distribution.  Useful
            when the same data is available at different access tiers (e.g. a
            public summary endpoint and a restricted raw-file endpoint).
        default_distribution: When ``True``, this distribution's ``url``,
            ``media_type``, and ``format`` are inlined into the parent Dataset
            response.  Exactly one distribution per Dataset should carry this
            flag.  Set by an appropriate admin; the first distribution created
            for a Dataset is promoted automatically.
    """

    url: str
    media_type: str | None = Field(default=None)
    format: str | None = Field(default=None)
    access_level: AccessLevel | None = Field(default=None)
    default_distribution: bool = Field(default=False)


class Distribution(DistributionBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    dataset_id: int | None = Field(
        default=None, foreign_key="dataset.id", index=True, ondelete="CASCADE"
    )

    dataset: "Dataset" = Relationship(back_populates="distributions")


class DistributionCreate(DistributionBase):
    pass


class DistributionRead(DistributionBase):
    id: int
    dataset_id: int | None
    storage_options: dict[str, Any] | None = None


class DistributionUpdate(SQLModel):
    url: str | None = None
    media_type: str | None = None
    format: str | None = None
    access_level: AccessLevel | None = None
    default_distribution: bool | None = None
