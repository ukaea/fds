from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator
from sqlmodel import Field, Relationship, SQLModel

from .storage_options import StorageOptions, StorageOptionsType

if TYPE_CHECKING:
    from .dataset import Dataset


def _http_url(value: str) -> str:
    parts = urlsplit(value)
    has_space = any(c.isspace() for c in value)
    if parts.scheme not in ("http", "https") or not parts.hostname or has_space:
        raise ValueError(
            "conforms_to must be an http or https URL naming a schema, such as "
            "https://github.com/iterorganization/IMAS-Data-Dictionary/tree/4.0.0"
        )
    return value


SchemaURI = Annotated[str, AfterValidator(_http_url)]


class DistributionBase(SQLModel):
    """A physical access path for a Dataset (maps to ``dcat:Distribution``).

    All distributions of the same dataset carry the same information: the same
    data in different serialisations, at different access paths, or in different
    schemas that each declares in ``conforms_to``.  Data that differs belongs in
    a separate Dataset.

    Fields:
        url: The download or access URL for this distribution
            (``dcat:downloadURL``).
        group: Path of the group inside the object at ``url`` that holds this
            Dataset, for a file that holds several Datasets as groups, e.g.
            ``"equilibrium"`` in a NetCDF file of a whole shot.  ``None`` when
            ``url`` addresses the Dataset on its own.
        conforms_to: http or https URL naming the schema this copy follows
            (``dct:conformsTo``), e.g. an IMAS Data Dictionary version as
            ``https://github.com/iterorganization/IMAS-Data-Dictionary/tree/4.0.0``.
            Distributions in different schemas carry the same information, but a
            reader must honour this to get the same values from each.
        endpoint_url: Storage endpoint hosting the data.  Used by FDS to look
            up the matching provider config for credential vending.
        region: Storage region for this distribution.  When set, overrides the
            matching provider config's region.  Useful for multi-region setups
            where one logical provider serves data across several regions.
        media_type: IANA media type / MIME type of the file, e.g.
            ``application/x-hdf5`` or ``text/csv``  (``dcat:mediaType``).
            Use this when you need machine-readable type identification — it
            must be a registered IANA media type string.
        format: Human-readable or controlled-vocabulary format label, e.g.
            ``"HDF5"``, ``"NetCDF-4"``, ``"CSV"``  (``dct:format``).
            Use this for display and discovery; it is not required to be an
            IANA media type.  Both fields may be populated simultaneously —
            ``media_type`` for interoperability, ``format`` for readability.
        default_distribution: When ``True``, this distribution's ``url``,
            ``media_type``, and ``format`` are inlined into the parent Dataset
            response.  Exactly one distribution per Dataset should carry this
            flag.  Set by an appropriate admin; the first distribution created
            for a Dataset is promoted automatically.
        storage_options_type: Discriminator selecting which consumer-library
            shape ``storage_options`` is rendered in (e.g. ``"fsspec_s3"`` for
            s3fs/xarray/zarr/pyarrow consumers, ``"icechunk_s3"`` for icechunk
            ``s3_storage`` consumers).  ``None`` means the distribution is
            accessed by its URL directly (e.g. an HTTPS download) and FDS will
            not generate ``storage_options`` for it.
    """

    url: str
    group: str | None = Field(default=None)
    conforms_to: SchemaURI | None = Field(default=None)
    endpoint_url: str | None = Field(default=None)
    region: str | None = Field(default=None)
    media_type: str | None = Field(default=None)
    format: str | None = Field(default=None)
    default_distribution: bool = Field(default=False)
    storage_options_type: StorageOptionsType | None = Field(default=None)


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
    storage_options: StorageOptions | None = None


class DistributionUpdate(SQLModel):
    url: str | None = None
    group: str | None = None
    conforms_to: SchemaURI | None = None
    endpoint_url: str | None = None
    region: str | None = None
    media_type: str | None = None
    format: str | None = None
    default_distribution: bool | None = None
    storage_options_type: StorageOptionsType | None = None
