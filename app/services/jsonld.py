from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.models.collection import Collection, CollectionRead
from app.models.dataset import Dataset, DatasetRead
from app.models.device import Device, DeviceRead
from app.models.distribution import Distribution
from app.models.shot import Shot, ShotRead

if TYPE_CHECKING:
    from app.models.activity import Activity

# Placeholder namespace for the Fusion Energy Lexicon (FuEL), still in
# development. FuEL supplies SKOS role concepts used as ``dcat:hadRole`` values on
# a ``dcat:qualifiedRelation``; ``fuel:geometry`` and
# ``fuel:calibration`` mark the two reference edges. Swap this single constant for
# the canonical FuEL URI once it is published.
FUEL_NAMESPACE = "https://w3id.org/fuel/ns#"

# FuEL role concepts marking a qualified relation's reference kind.
FUEL_GEOMETRY_ROLE = "fuel:geometry"
FUEL_CALIBRATION_ROLE = "fuel:calibration"
FUEL_ANNOTATION_ROLE = "fuel:annotation"

METADATA_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "fuel": FUEL_NAMESPACE,
    "schema": "https://schema.org/",
    "time": "http://www.w3.org/2006/time#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dqv": "http://www.w3.org/ns/dqv#",
    "oa": "http://www.w3.org/ns/oa#",
    "title": "dct:title",
    "description": "dct:description",
    "publisher": "dct:publisher",
    "identifier": "dct:identifier",
    "created": {"@id": "dct:created", "@type": "xsd:dateTime"},
    "modified": {"@id": "dct:modified", "@type": "xsd:dateTime"},
    "creator": "dct:creator",
    "startDate": {"@id": "dcat:startDate", "@type": "xsd:dateTime"},
    "endDate": {"@id": "dcat:endDate", "@type": "xsd:dateTime"},
    "keywords": "dcat:keyword",
    "license": "dct:license",
    "version": "dcat:version",
    "accessRights": "dct:accessRights",
    "dataset": {"@id": "dcat:dataset", "@type": "@id"},
    "service": {"@id": "dcat:service", "@type": "@id"},
    "catalog": {"@id": "dcat:catalog", "@type": "@id"},
    "mediaType": "dcat:mediaType",
    "format": "dct:format",
}


def generate_context() -> dict[str, Any]:
    """
    Returns the JSON-LD @context for FDS metadata.
    """
    return METADATA_CONTEXT


def _map_scientific_metadata_to_jsonld(metadata: list[Any]) -> list[dict[str, Any]]:
    result = []
    for prop in metadata:
        name = prop["name"] if isinstance(prop, dict) else prop.name
        value = prop["value"] if isinstance(prop, dict) else prop.value
        unit = prop.get("unit") if isinstance(prop, dict) else prop.unit
        desc = prop.get("description") if isinstance(prop, dict) else prop.description
        extent = prop.get("extent") if isinstance(prop, dict) else prop.extent
        node: dict[str, Any] = {
            "@type": "schema:PropertyValue",
            "schema:name": name,
            "schema:value": value,
        }
        if unit is not None:
            node["schema:unitText"] = unit
        if desc is not None:
            node["schema:description"] = desc
        if extent is not None:
            _apply_extent_to_node(node, extent)
        result.append(node)
    return result


# Unit strings that map to a W3C Time TemporalUnit individual. W3C Time defines
# individuals down to the second only, so sub-second units (ms/us/ns) have none
# and fall back to schema:unitText on the time:TimePosition.
_W3C_TEMPORAL_UNIT = {
    "s": "time:unitSecond",
    "min": "time:unitMinute",
    "h": "time:unitHour",
    "d": "time:unitDay",
    "wk": "time:unitWeek",
    "mo": "time:unitMonth",
    "yr": "time:unitYear",
}


def _extent_fields(extent: Any) -> tuple[str, float, float | None, str | None]:
    """Read ``(dimension, start, end, unit)`` from an ``Extent`` dict or model."""
    if isinstance(extent, dict):
        return (
            extent["dimension"],
            extent["start"],
            extent.get("end"),
            extent.get("unit"),
        )
    return extent.dimension, extent.start, extent.end, extent.unit


def _apply_extent_to_node(node: dict[str, Any], extent: Any) -> None:
    """Localise a ``schema:PropertyValue`` node with a 1D ``Extent``.

    A ``time`` dimension projects to a W3C Time ``time:Interval`` via
    ``time:hasTime``; any other dimension projects to a generic numeric range
    under ``schema:valueReference``.
    """
    dimension, start, end, unit = _extent_fields(extent)
    if dimension == "time":
        node["time:hasTime"] = _time_interval_node(start, end, unit)
    else:
        node["schema:valueReference"] = _numeric_range_node(dimension, start, end, unit)


def _time_instant(position: float, unit: str | None) -> dict[str, Any]:
    """A ``time:Instant`` at ``position`` on the time axis.

    Carries a ``time:TimePosition`` with ``time:numericPosition`` and, when the
    unit is a known W3C temporal unit, ``time:unitType`` (else ``schema:unitText``
    for a non-standard unit; nothing when no unit is given).
    """
    time_position: dict[str, Any] = {
        "@type": "time:TimePosition",
        "time:numericPosition": position,
    }
    w3c_unit = _W3C_TEMPORAL_UNIT.get(unit) if unit is not None else None
    if w3c_unit is not None:
        time_position["time:unitType"] = {"@id": w3c_unit}
    elif unit is not None:
        time_position["schema:unitText"] = unit
    return {"@type": "time:Instant", "time:inTimePosition": time_position}


def _time_interval_node(
    start: float, end: float | None, unit: str | None
) -> dict[str, Any]:
    """A W3C Time ``time:Interval``; a beginning-only instant when ``end`` is None."""
    node: dict[str, Any] = {
        "@type": "time:Interval",
        "time:hasBeginning": _time_instant(start, unit),
    }
    if end is not None:
        node["time:hasEnd"] = _time_instant(end, unit)
    return node


def _numeric_range_node(
    dimension: str, start: float, end: float | None, unit: str | None
) -> dict[str, Any]:
    """A non-time ``Extent`` as a generic numeric range ``schema:PropertyValue``.

    A range (``end`` given) uses ``schema:minValue``/``schema:maxValue``; a point
    (``end`` None) uses ``schema:value``. The dimension name is ``schema:name``.
    """
    node: dict[str, Any] = {
        "@type": "schema:PropertyValue",
        "schema:name": dimension,
    }
    if end is not None:
        node["schema:minValue"] = start
        node["schema:maxValue"] = end
    else:
        node["schema:value"] = start
    if unit is not None:
        node["schema:unitText"] = unit
    return node


def map_device_to_dcat(device: Device | DeviceRead, base_url: str) -> dict[str, Any]:
    """
    Maps a Device to a dcat:Catalog.
    """
    device_uri = f"{base_url}/api/v1/devices/{device.name}"

    data = {
        "@context": METADATA_CONTEXT,
        "@type": "dcat:Catalog",
        "@id": device_uri,
        "title": device.title or f"Device: {device.name}",
        "description": device.description or f"Data catalog for device {device.name}",
        "identifier": device.name,
        "publisher": device.publisher,
        "creator": device.creator,
        "created": device.created_at.isoformat()
        if hasattr(device, "created_at")
        else None,
        "modified": device.updated_at.isoformat()
        if hasattr(device, "updated_at")
        else None,
    }

    return {k: v for k, v in data.items() if v is not None}


def map_shot_to_dcat(
    shot: Shot | ShotRead,
    base_url: str,
    annotations: "list[DatasetRead] | None" = None,
) -> dict[str, Any]:
    """Maps a Shot to a dcat:Dataset JSON-LD document."""
    shot_uri = f"{base_url}/api/v1/devices/{shot.device_name}/shots/{shot.id}"
    data: dict[str, Any] = {
        "@context": METADATA_CONTEXT,
        "@type": "dcat:Dataset",
        "@id": shot_uri,
        "title": f"Shot {shot.id}",
        "description": shot.description,
        "identifier": shot.id,
        "publisher": shot.publisher,
        "creator": shot.creator,
        "created": shot.created_at.isoformat() if hasattr(shot, "created_at") else None,
        "modified": shot.updated_at.isoformat()
        if hasattr(shot, "updated_at")
        else None,
    }
    # dct:temporal → dct:PeriodOfTime. Emit a closed period when an end is known or
    # derivable from the duration; otherwise an open period (start only).
    if shot.shot_at:
        end = shot.shot_end
        if end is None and shot.shot_duration is not None:
            end = shot.shot_at + timedelta(seconds=shot.shot_duration)
        period: dict[str, Any] = {
            "@type": "dct:PeriodOfTime",
            "startDate": shot.shot_at.isoformat(),
        }
        if end is not None:
            period["endDate"] = end.isoformat()
        data["dct:temporal"] = period
    if shot.access_level:
        data["accessRights"] = shot.access_level.value
    sci_meta = getattr(shot, "scientific_metadata", None)
    if sci_meta:
        data["schema:additionalProperty"] = _map_scientific_metadata_to_jsonld(sci_meta)
    resolved_annotations: list[Any] = (
        annotations if annotations is not None else getattr(shot, "annotations", None)
    ) or []
    if resolved_annotations:
        data["dcat:qualifiedRelation"] = [
            _qualified_relation(version, FUEL_ANNOTATION_ROLE, base_url)
            for version in resolved_annotations
        ]
    return {k: v for k, v in data.items() if v is not None}


def map_dataset_to_dcat(
    dataset: Dataset | DatasetRead,
    base_url: str,
    geometry: "list[DatasetRead] | None" = None,
    calibration: "list[DatasetRead] | None" = None,
    annotations: "list[DatasetRead] | None" = None,
) -> dict[str, Any]:
    """
    Maps a Dataset to a dcat:Dataset.

    ``geometry`` / ``calibration`` supply resolved reference versions when the
    source object does not itself carry them (e.g. an ORM ``Dataset``). Both link
    via a ``dcat:qualifiedRelation`` carrying a FuEL role — ``fuel:geometry`` or
    ``fuel:calibration`` (calibration one per chain stage, in order).
    """
    # Construct URI
    # Note: Using the API path as the URI
    dataset_uri = (
        f"{base_url}/api/v1/datasets/{dataset.id}"
        if hasattr(dataset, "id") and dataset.id
        else None
    )

    data = {
        "@context": METADATA_CONTEXT,
        "@type": "dcat:Dataset",
        "@id": dataset_uri,
        "title": dataset.title or dataset.name,
        "description": dataset.description,
        "identifier": str(dataset.id) if hasattr(dataset, "id") else dataset.name,
        "publisher": dataset.publisher,
        "creator": dataset.creator,
        "created": dataset.created_at.isoformat()
        if hasattr(dataset, "created_at")
        else None,
        "modified": dataset.updated_at.isoformat()
        if hasattr(dataset, "updated_at")
        else None,
        "keywords": dataset.keywords.split(",") if dataset.keywords else [],
        "license": dataset.license,
        "version": dataset.version,
    }

    if dataset.access_level:
        data["accessRights"] = dataset.access_level.value

    if dataset.quality_flag:
        data["dqv:hasQualityAnnotation"] = {
            "@type": "dqv:QualityAnnotation",
            "oa:motivatedBy": {"@id": "dqv:qualityAssessment"},
            "oa:hasBody": dataset.quality_flag,
        }

    # dct:temporal → dct:PeriodOfTime
    if dataset.temporal_start or dataset.temporal_end:
        period: dict[str, Any] = {"@type": "dct:PeriodOfTime"}
        if dataset.temporal_start:
            period["startDate"] = dataset.temporal_start.isoformat()
        if dataset.temporal_end:
            period["endDate"] = dataset.temporal_end.isoformat()
        data["dct:temporal"] = period

    # DCAT Distribution mapping
    distributions: list[Distribution] = getattr(dataset, "distributions", []) or []
    if distributions:
        dist_nodes = []
        for dist in distributions:
            node: dict[str, Any] = {"@type": "dcat:Distribution"}
            if dist.url.startswith(("http://", "https://")):
                # Public HTTPS: accessURL = downloadURL = the URL
                node["dcat:accessURL"] = dist.url
                node["dcat:downloadURL"] = dist.url
            else:
                # Cloud storage: accessURL = FDS credential-vending endpoint, downloadURL = raw URI
                node["dcat:accessURL"] = dataset_uri
                node["dcat:downloadURL"] = dist.url
            if dist.media_type:
                node["dcat:mediaType"] = dist.media_type
            if dist.format:
                node["dct:format"] = dist.format
            if dist.access_level:
                node["dct:accessRights"] = dist.access_level.value
            dist_nodes.append(node)
        data["dcat:distribution"] = dist_nodes
        # Convenience shorthand: downloadURL of the default distribution (HTTP/S only)
        default = next((d for d in distributions if d.default_distribution), None)
        if default and default.url.startswith(("http://", "https://")):
            data["dcat:downloadURL"] = default.url

    # PROV-O Mapping (Provenance)
    # Embed the Activity as prov:wasGeneratedBy if the relationship is loaded
    activity: "Activity | None" = getattr(dataset, "activity", None)
    if activity:
        source_uri = f"{base_url}/api/v1/sources/{activity.source_id}"
        prov_node: dict[str, Any] = {
            "@type": "prov:Activity",
            "prov:type": activity.activity_type,
            "prov:wasAssociatedWith": {
                "@id": source_uri,
                "@type": "prov:SoftwareAgent",
                "dct:title": activity.source.name if activity.source else None,
                "dct:description": activity.source.description
                if activity.source
                else None,
                "dcat:version": activity.source_version,
            },
        }
        if activity.started_at:
            prov_node["prov:startedAtTime"] = activity.started_at.isoformat()
        if activity.ended_at:
            prov_node["prov:endedAtTime"] = activity.ended_at.isoformat()
        if activity.parameters:
            prov_node["prov:value"] = activity.parameters
        input_datasets = getattr(activity, "input_datasets", None) or []
        if input_datasets:
            prov_node["prov:used"] = [
                {
                    "@id": f"{base_url}/api/v1/datasets/{ds.id}",
                    "@type": "prov:Entity",
                }
                for ds in input_datasets
            ]
        data["prov:wasGeneratedBy"] = prov_node

    sci_meta = getattr(dataset, "scientific_metadata", None)
    if sci_meta:
        data["schema:additionalProperty"] = _map_scientific_metadata_to_jsonld(sci_meta)

    # Link resolved reference versions as qualified relations, each tagged with its
    # FuEL role: geometry via fuel:geometry, calibration (in stage order) via
    # fuel:calibration. Both kinds share the one dcat:qualifiedRelation array.
    resolved_geometry: list[Any] = (
        geometry if geometry is not None else getattr(dataset, "geometry", None)
    ) or []
    resolved_calibration: list[Any] = (
        calibration
        if calibration is not None
        else getattr(dataset, "calibration", None)
    ) or []
    resolved_annotations: list[Any] = (
        annotations
        if annotations is not None
        else getattr(dataset, "annotations", None)
    ) or []
    qualified_relations = (
        [
            _qualified_relation(version, FUEL_GEOMETRY_ROLE, base_url)
            for version in resolved_geometry
        ]
        + [
            _qualified_relation(version, FUEL_CALIBRATION_ROLE, base_url)
            for version in resolved_calibration
        ]
        + [
            _qualified_relation(version, FUEL_ANNOTATION_ROLE, base_url)
            for version in resolved_annotations
        ]
    )
    if qualified_relations:
        data["dcat:qualifiedRelation"] = qualified_relations

    return {k: v for k, v in data.items() if v is not None}


def _qualified_relation(
    version: "DatasetRead", role: str, base_url: str
) -> dict[str, Any]:
    """A resolved reference version as a dcat:Relationship carrying its FuEL role."""
    return {
        "@type": "dcat:Relationship",
        "dcat:hadRole": {"@id": role},
        "dct:relation": _map_reference_version(version, base_url),
    }


def _map_reference_version(version: "DatasetRead", base_url: str) -> dict[str, Any]:
    """A resolved reference version (geometry or calibration) as a linked node."""
    node: dict[str, Any] = {
        "@id": f"{base_url}/api/v1/datasets/{version.id}",
        "@type": "dcat:Dataset",
        "dct:title": version.title or version.name,
    }
    coverage = getattr(version, "applies_to", None)
    period = _coverage_to_period(coverage)
    if period is not None:
        node["dct:temporal"] = period
    return node


def _coverage_to_period(coverage: Any) -> dict[str, Any] | None:
    """Map a coverage's date ranges to a dct:PeriodOfTime, if it has any."""
    if coverage is None:
        return None
    date_ranges = (
        coverage.get("date_ranges")
        if isinstance(coverage, dict)
        else getattr(coverage, "date_ranges", None)
    )
    if not date_ranges:
        return None
    first = date_ranges[0]
    from_date = first["from_date"] if isinstance(first, dict) else first.from_date
    to_date = first.get("to_date") if isinstance(first, dict) else first.to_date
    if isinstance(from_date, str):
        start = from_date
    else:
        start = from_date.isoformat()
    period: dict[str, Any] = {"@type": "dct:PeriodOfTime", "startDate": start}
    if to_date is not None:
        period["endDate"] = to_date if isinstance(to_date, str) else to_date.isoformat()
    return period


def map_collection_to_dcat(
    collection: Collection | CollectionRead, base_url: str
) -> dict[str, Any]:
    """Maps a Collection to a ``dcat:Catalog`` JSON-LD document.

    Member Datasets are serialised as ``dcat:dataset`` references (``@id``
    only — full Dataset documents are available at their own URIs). Nested
    child Collections are serialised as ``dcat:catalog`` references. The
    producing Activity, if present, is embedded as a ``prov:wasGeneratedBy``
    node, consistent with the Dataset serialisation in ``map_dataset_to_dcat``.
    """
    collection_id = getattr(collection, "id", None)
    collection_uri = (
        f"{base_url}/api/v1/collections/{collection_id}" if collection_id else None
    )

    data: dict[str, Any] = {
        "@context": METADATA_CONTEXT,
        "@type": "dcat:Catalog",
        "@id": collection_uri,
        "title": collection.title or collection.name,
        "description": collection.description,
        "identifier": str(collection_id) if collection_id else collection.name,
        "publisher": collection.publisher,
        "creator": collection.creator,
        "created": collection.created_at.isoformat()
        if hasattr(collection, "created_at")
        else None,
        "modified": collection.updated_at.isoformat()
        if hasattr(collection, "updated_at")
        else None,
    }

    if collection.access_level:
        data["accessRights"] = collection.access_level.value

    # Collection root → dcat:distribution (DCAT 3: dcat:Catalog is a dcat:Dataset subclass)
    # root_url is the format-agnostic access root for all physical data in this collection.
    root_url: str | None = getattr(collection, "root_url", None)
    if root_url:
        data["dcat:distribution"] = {
            "@type": "dcat:Distribution",
            "dcat:accessURL": root_url,
        }

    # Member Datasets → dcat:dataset references
    member_datasets: list[Any] = getattr(collection, "datasets", []) or []
    if member_datasets:
        data["dcat:dataset"] = [
            {
                "@id": f"{base_url}/api/v1/datasets/{ds.id}",
                "@type": "dcat:Dataset",
                "dct:title": ds.title or ds.name,
            }
            for ds in member_datasets
            if getattr(ds, "id", None)
        ] or None

    # Child Collections → dcat:catalog references
    child_collections: list[Any] = getattr(collection, "child_collections", []) or []
    if child_collections:
        data["dcat:catalog"] = [
            {
                "@id": f"{base_url}/api/v1/collections/{c.id}",
                "@type": "dcat:Catalog",
                "dct:title": c.title or c.name,
            }
            for c in child_collections
            if getattr(c, "id", None)
        ] or None

    # PROV-O provenance — embed the producing Activity if present
    activity: "Activity | None" = getattr(collection, "activity", None)
    if activity:
        source_uri = f"{base_url}/api/v1/sources/{activity.source_id}"
        prov_node: dict[str, Any] = {
            "@type": "prov:Activity",
            "prov:type": activity.activity_type,
            "prov:wasAssociatedWith": {
                "@id": source_uri,
                "@type": "prov:SoftwareAgent",
                "dct:title": activity.source.name if activity.source else None,
                "dct:description": activity.source.description
                if activity.source
                else None,
                "dcat:version": activity.source_version,
            },
        }
        if activity.started_at:
            prov_node["prov:startedAtTime"] = activity.started_at.isoformat()
        if activity.ended_at:
            prov_node["prov:endedAtTime"] = activity.ended_at.isoformat()
        if activity.parameters:
            prov_node["prov:value"] = activity.parameters
        data["prov:wasGeneratedBy"] = prov_node

    return {k: v for k, v in data.items() if v is not None}
