from pydantic import BaseModel, Field

from fds.models.activity import ActivityType


class RecordFilters(BaseModel):
    """The filters every dataset and collection listing takes, in this catalogue
    or in another one."""

    name: str | None = Field(
        None,
        description="Keep the records with this name. A name that matches nothing "
        "gives an empty page.",
    )
    properties: list[str] = Field(
        default_factory=list,
        alias="property",
        description="Keep the records whose own `scientific_metadata` has this "
        "property: `elm` for any value, `elm:type-I` for that one. A property inside "
        "a group is named by its path, the names joined by `.`: "
        "`nbi.beam.source:SW`. Repeat it: values of one property match either, "
        "different properties must all match.",
    )
    activity_type: ActivityType | None = Field(
        None,
        description="Keep the records whose `activity_id` names an Activity of this "
        "type, such as `simulation`.",
    )
    source: str | None = Field(
        None,
        description="Keep the records whose `activity_id` names an Activity carried "
        "out by the source with this name, such as `jintrac`.",
    )
    include_replaced: bool = Field(
        False,
        description="List a record even when you may read a record that replaces it.",
    )


class LocalFilters(RecordFilters):
    """The filters of this catalogue's own listings, which can name its records."""

    activity_id: int | None = Field(
        None, description="Keep the records whose `activity_id` is this Activity."
    )


class ShotSpanFilters(BaseModel):
    """The filters of a listing that spans shots: every record, or a device's."""

    shot_id_prefix: str | None = Field(
        None,
        description="Keep the records on a shot whose ID starts with this, so `304` "
        "finds those on shots 30420 and 30421. A record on no shot never matches.",
    )


class DatasetShotSpanFilters(ShotSpanFilters):
    shot_properties: list[str] = Field(
        default_factory=list,
        alias="shot_property",
        description="Keep the datasets whose shot has this property, in the forms "
        "`property` takes. With `name` it spans both levels: "
        "`?name=equilibrium&shot_property=elm` finds the equilibrium datasets of "
        "shots that had ELMs. A dataset on no shot never matches.",
    )


class DatasetIncludes(BaseModel):
    """What a dataset read can carry besides the dataset."""

    include_storage_options: bool = Field(
        False,
        description="Add `storage_options`: short-lived credentials for reading "
        "each dataset's storage.",
    )
    include_geometry: bool = Field(
        False,
        description="Add `geometry`: the versions each dataset's "
        "`geometry_references` resolve to for its shot.",
    )
    include_calibration: bool = Field(
        False,
        description="Add `calibration`: the versions each dataset's "
        "`calibration_references` resolve to for its shot, by ascending "
        "`calibration_stage`.",
    )
    include_annotations: bool = Field(
        False, description="Add `annotations`: the datasets that annotate each one."
    )
