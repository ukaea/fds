from datetime import datetime
from typing import TYPE_CHECKING

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

from .mixins import DescriptiveMixin, TimestampMixin
from .policy import AccessLevel
from .reference import ReferenceCoverage
from .scientific_metadata import ScientificProperty
from .storage_options import StorageOptions, StorageOptionsType

if TYPE_CHECKING:
    from .activity import Activity
    from .distribution import Distribution, DistributionRead
    from .shot import Shot


class DatasetBase(DescriptiveMixin, TimestampMixin, SQLModel):
    """Core metadata for a dataset (maps to ``dcat:Dataset``).

    A Dataset is a metadata container describing *what* the data is.  The
    physical access paths (how to retrieve it) live in associated
    ``Distribution`` rows.  In the REST API the default distribution's fields
    are inlined here for convenience; alternatives are exposed in ``formats``.

    Fields:
        name: Stable, URL-safe identifier within the scope of a Shot/device.
            Immutable once created (see ADR-0026).
        level: Numeric processing level (e.g. 0 = raw, 1 = calibrated).
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
    level: int = Field(index=True)
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
    scientific_metadata: list[ScientificProperty] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
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
    applies_to: ReferenceCoverage | None = Field(
        default=None,
        description=(
            "For a reference-resource version (geometry, calibration, …): which "
            "shots this version covers. Shared across kinds; coverage must not "
            "overlap another version of the same role within a kind."
        ),
        sa_column=Column(JSON, nullable=True),
    )


class Dataset(DatasetBase, table=True):
    __table_args__ = (
        ForeignKeyConstraint(
            ["device_name", "shot_id"],
            ["shot.device_name", "shot.id"],
        ),
        # Unattributed datasets: one per (name, context, origin).
        # Allows federated catalogs to each contribute a same-named dataset.
        Index(
            "idx_dataset_unique_no_activity",
            "name",
            "device_name",
            "shot_id",
            "origin",
            unique=True,
            sqlite_where=text("activity_id IS NULL"),
            postgresql_where=text("activity_id IS NULL"),
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
            sqlite_where=text("activity_id IS NOT NULL"),
            postgresql_where=text("activity_id IS NOT NULL"),
        ),
    )
    id: int | None = Field(default=None, primary_key=True)
    shot_id: str | None = Field(default=None, index=True)
    activity_id: int | None = Field(default=None, foreign_key="activity.id", index=True)
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
    origin: str | None = None
    # Default distribution fields — passed through to a Distribution row with
    # default_distribution=True on create.  Only created when url is supplied.
    url: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    media_type: str | None = None
    format: str | None = None
    storage_options_type: StorageOptionsType | None = None


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
    applies_to: ReferenceCoverage | None = None
