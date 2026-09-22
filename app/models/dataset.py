from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Self

from pydantic import model_validator
from sqlmodel import (
    JSON,
    Column,
    Field,
    ForeignKeyConstraint,
    Index,
    Relationship,
    SQLModel,
    text,
)

from .coverage import Coverage
from .mixins import DescriptiveMixin, ScientificMetadataMixin, TimestampMixin
from .policy import AccessLevel
from .scientific_metadata import ScientificProperty
from .storage_options import StorageOptions, StorageOptionsType

if TYPE_CHECKING:
    from .activity import Activity
    from .distribution import Distribution, DistributionRead
    from .shot import Shot


class DatasetScope(str, Enum):
    """Which datasets a device listing returns.

    - ALL: every dataset hosted by the device, device-level and shot-level.
    - DEVICE: only datasets that belong to the device as a whole rather than
      to any one shot.
    - SHOT: only datasets attached to one of the device's shots.
    """

    ALL = "all"
    DEVICE = "device"
    SHOT = "shot"


class DatasetBase(DescriptiveMixin, ScientificMetadataMixin, TimestampMixin, SQLModel):
    """Core metadata for a dataset (maps to ``dcat:Dataset``).

    A Dataset is a metadata container describing *what* the data is.  The
    physical access paths (how to retrieve it) live in associated
    ``Distribution`` rows.  In the REST API the default distribution's fields
    are inlined here for convenience; alternatives are exposed in ``formats``.

    Fields:
        name: Stable, URL-safe identifier within the scope of a Shot/device.
            Immutable once created.
        level: Numeric processing level.  Optional: there is no controlled
            vocabulary for processing levels yet, so a dataset carries one only
            where the producer has a meaning for it.
        quality_flag: Free-form quality annotation (e.g. ``"good"``,
            ``"suspect"``).
        device_name: Name of the device that produced this dataset.
        access_level: Default access policy.  ``None`` means inherit from the
            enclosing Shot or device policy.
        license: SPDX identifier or URL for the data licence.
        version: Dataset version string.
        keywords: Comma-separated discovery keywords.
        required_scopes: OAuth scopes required to read this dataset when access
            is restricted.  ``None`` inherits from the enclosing Shot/device
            policy.
        allowed_idps: Trusted identity-provider issuer allowlist.  ``None``
            inherits from the enclosing Shot/device policy.
    """

    name: str = Field(index=True)
    level: int | None = Field(default=None, index=True)
    quality_flag: str | None = Field(default=None, index=True)
    temporal_start: datetime | None = Field(default=None)
    temporal_end: datetime | None = Field(default=None)
    device_name: str | None = Field(default=None, index=True)
    access_level: AccessLevel | None = Field(default=None, index=True)
    license: str | None = Field(default=None)
    version: str | None = Field(default=None, index=True)
    keywords: str | None = Field(default=None)  # Comma-separated list
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this dataset when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this dataset. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
        sa_column=Column(JSON, nullable=True),
    )

    geometry_references: list[str] | None = Field(
        default=None,
        description=(
            "For a signal dataset: the geometry roles it uses (e.g. "
            "['thomson_positions']). Names roles, not versions; resolution finds "
            "the correct version per shot at read time."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    geometry_roles: list[str] | None = Field(
        default=None,
        description=(
            "For a geometry version (a device-level dataset): the geometry "
            "components it provides. Usually one, but a bundled store may provide "
            "several."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    calibration_references: list[str] | None = Field(
        default=None,
        description=(
            "For a signal dataset: the calibration roles it uses. Names roles, not "
            "versions; resolution finds the applicable version(s) per shot at read "
            "time. A role may resolve to an ordered chain of stages (see "
            "calibration_stage)."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    calibration_roles: list[str] | None = Field(
        default=None,
        description=(
            "For a calibration version (a device-level dataset): the calibration "
            "components it provides."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    calibration_stage: int | None = Field(
        default=None,
        description=(
            "For a calibration version: its position in an ordered calibration "
            "chain (lower applies first). Non-overlap is enforced per (role, "
            "stage), so different stages of a role may cover the same shot. None "
            "for single-stage calibration."
        ),
    )
    applies_to: Coverage | None = Field(
        default=None,
        description=(
            "For a reference-resource version (geometry, calibration, …): which "
            "shots this version covers. Shared across kinds; coverage must not "
            "overlap another version of the same role within a kind."
        ),
        sa_column=Column(JSON, nullable=True),
    )
    annotates: str | None = Field(
        default=None,
        index=True,
        description=(
            "For a feature annotation dataset: the feature it localises (e.g. 'elm'). "
            "Marks the dataset as an annotation and matches the inline annotation of the "
            "same name on its subject. "
            "The subject fixes the frame: subject_dataset_id (dataset frame) or the "
            "annotation's own shot_id (shot frame). Coordinates live in the "
            "annotation's data, in that frame."
        ),
    )


class Dataset(DatasetBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["device_name", "shot_id"],
            ["shot.device_name", "shot.id"],
        ),
        # Unattributed datasets: one per (name, context) minted here, and one per
        # (name, context, origin) from each federated catalogue. Two indexes
        # because SQL treats NULLs as distinct, so a single index over origin
        # would not catch a duplicate local dataset.
        Index(
            "idx_dataset_unique_local",
            "name",
            "device_name",
            "shot_id",
            unique=True,
            postgresql_where=text("activity_id IS NULL AND origin IS NULL"),
        ),
        Index(
            "idx_dataset_unique_federated",
            "name",
            "device_name",
            "shot_id",
            "origin",
            unique=True,
            postgresql_where=text("activity_id IS NULL AND origin IS NOT NULL"),
        ),
        # Attributed datasets: one per (name, context, activity).
        # Allows multiple runs (different activity_ids) to each produce same-named datasets.
        Index(
            "idx_dataset_unique_with_activity",
            "name",
            "device_name",
            "shot_id",
            "activity_id",
            unique=True,
            postgresql_where=text("activity_id IS NOT NULL"),
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    shot_id: str | None = Field(default=None, index=True)
    activity_id: int | None = Field(default=None, foreign_key="activity.id", index=True)
    subject_dataset_id: int | None = Field(
        default=None,
        foreign_key="dataset.id",
        index=True,
        description=(
            "For a feature annotation linked to a specific Dataset: the source Dataset "
            "this annotation localises a feature in. Null for a shot-frame "
            "annotation, whose subject is the shot it belongs to."
        ),
    )
    # The catalogue a federated record came from. NULL means it was minted in this FDS instance.
    origin: str | None = Field(default=None, index=True)

    shot: "Shot" = Relationship(
        back_populates="datasets",
        sa_relationship_kwargs={
            "primaryjoin": "and_(Dataset.shot_id==Shot.id, Dataset.device_name==Shot.device_name)",
            "foreign_keys": "[Dataset.shot_id, Dataset.device_name]",
        },
    )
    activity: "Activity" = Relationship(back_populates="datasets")
    distributions: list["Distribution"] = Relationship(
        back_populates="dataset",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    derivations: list["DatasetDerivation"] = Relationship(
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "primaryjoin": "Dataset.id==DatasetDerivation.dataset_id",
        },
    )


class DatasetDerivationBase(SQLModel):
    """An asserted upstream that a Dataset was derived from (``prov:wasDerivedFrom``).

    The upstream need not be registered in FDS. It is identified in whichever of
    three ways the producer can manage, so partial provenance can still be
    recorded: by ``source_dataset_id`` when it is a registered Dataset, by
    ``source_identifier`` when it has a DOI, URL or other PID, or by
    ``source_label`` and ``source_description`` alone when it can only be named
    or described.

    ``source_dataset_id`` and ``source_identifier`` are mutually exclusive: a
    registered dataset is referenced by its FDS URI, and its own PID belongs on
    that dataset. At least one of the three must be present. Label and
    description may accompany any of them.
    """

    source_dataset_id: int | None = Field(
        default=None, foreign_key="dataset.id", index=True
    )
    source_identifier: str | None = Field(default=None, index=True)
    source_label: str | None = Field(default=None)
    source_description: str | None = Field(default=None)


class DatasetDerivation(DatasetDerivationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="dataset.id", index=True)


class DatasetDerivationCreate(DatasetDerivationBase):
    """An upstream to assert, either inline on the dataset or afterwards."""

    @model_validator(mode="after")
    def identifies_its_upstream_exactly_once(self) -> Self:
        if self.source_dataset_id is not None and self.source_identifier:
            raise ValueError(
                "a derivation names either source_dataset_id or source_identifier, "
                "not both: a registered dataset is referenced by its FDS URI"
            )
        if not any(
            (
                self.source_dataset_id is not None,
                self.source_identifier,
                self.source_label,
                self.source_description,
            )
        ):
            raise ValueError(
                "a derivation must identify its upstream by source_dataset_id, "
                "source_identifier, or at least a source_label or source_description"
            )
        return self


class DatasetDerivationRead(DatasetDerivationBase):
    id: int
    dataset_id: int


class DatasetLineageNode(SQLModel):
    """One entity in an upstream lineage walk, with its own upstreams nested.

    A node is whichever of three things the asserted derivation identified: a
    registered Dataset (``dataset_id`` and ``name``), an external entity with a
    persistent identifier (``identifier``), or an entity that could only be named
    or described (``label``, ``description``). Only a registered Dataset has
    upstreams of its own to nest.

    Three flags mark a branch that stops early, so a truncated chain is never
    mistaken for a complete one:

    - ``seen``: this dataset is expanded in full elsewhere in the same response.
      Repeats are not re-expanded, which keeps a diamond from duplicating its
      shared ancestor and makes a cycle terminate rather than recurse.
    - ``restricted``: the caller may not read this dataset, so its name and its
      own upstreams are withheld.
    - ``missing``: the derivation points at a dataset that no longer exists.
    """

    dataset_id: int | None = None
    name: str | None = None
    identifier: str | None = None
    label: str | None = None
    description: str | None = None
    seen: bool | None = None
    restricted: bool | None = None
    missing: bool | None = None
    derived_from: list["DatasetLineageNode"] = Field(default_factory=list)


class DatasetCreate(DatasetBase):
    """Schema for creating a Dataset.

    The fields below the dataset metadata are convenience pass-throughs that
    describe the initial default ``Distribution`` created alongside the dataset.
    Supplying ``url`` is optional — a Dataset can be registered without any
    physical distribution and distributions added later via the distributions
    sub-resource.
    """

    shot_id: str | None = None
    activity_id: int | None = None
    subject_dataset_id: int | None = None
    origin: str | None = None
    # Default distribution fields — passed through to a Distribution row with
    # default_distribution=True on create.  Only created when url is supplied.
    url: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    media_type: str | None = None
    format: str | None = None
    storage_options_type: StorageOptionsType | None = None
    derived_from: list[DatasetDerivationCreate] = Field(default_factory=list)


class DatasetRead(DatasetBase):
    """Dataset response schema.

    ``url``, ``media_type``, ``format``, and ``storage_options`` are
    denormalised from the default distribution for convenience.
    ``distributions`` lists all distributions associated with the dataset,
    including the default one (identified by ``default_distribution=True``).
    In JSON-LD responses these fields are re-separated into proper
    ``dcat:Dataset`` and ``dcat:distribution`` nodes.
    """

    id: int
    shot_id: str | None = None
    activity_id: int | None = None
    subject_dataset_id: int | None = None
    origin: str | None = None
    effective_access_level: AccessLevel | None = None
    # Default distribution fields inlined for convenience (None when no distribution exists)
    url: str | None = None
    media_type: str | None = None
    format: str | None = None
    storage_options: StorageOptions | None = None
    # All distributions (default flagged via default_distribution=True)
    distributions: list["DistributionRead"] | None = None
    geometry: list["DatasetRead"] | None = None
    calibration: list["DatasetRead"] | None = None
    annotations: list["DatasetRead"] | None = None


class DatasetUpdate(SQLModel):
    name: str | None = None
    level: int | None = None
    quality_flag: str | None = None
    temporal_start: datetime | None = None
    temporal_end: datetime | None = None
    device_name: str | None = None
    shot_id: str | None = None
    activity_id: int | None = None
    access_level: AccessLevel | None = None
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    license: str | None = None
    version: str | None = None
    keywords: str | None = None
    required_scopes: list[str] | None = Field(
        default=None,
        description=(
            "OAuth scopes required to read this dataset when access is restricted. "
            "If null, scope requirements inherit from the enclosing shot or device "
            "policy."
        ),
    )
    allowed_idps: list[str] | None = Field(
        default=None,
        description=(
            "Trusted issuer allowlist for this dataset. If null, allowed issuers "
            "inherit from the enclosing shot or device policy."
        ),
    )
    scientific_metadata: list[ScientificProperty] | None = None
    geometry_references: list[str] | None = None
    geometry_roles: list[str] | None = None
    calibration_references: list[str] | None = None
    calibration_roles: list[str] | None = None
    calibration_stage: int | None = None
    applies_to: Coverage | None = None
    annotates: str | None = None
    subject_dataset_id: int | None = None
