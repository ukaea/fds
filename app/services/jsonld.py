from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.models.activity import AgentRole
from app.models.collection import Collection, CollectionRead
from app.models.dataset import Dataset, DatasetRead
from app.models.device import Device, DeviceRead
from app.models.distribution import Distribution
from app.models.shot import Shot, ShotRead
from app.models.source import Source, SourceKind

if TYPE_CHECKING:
    from app.models.activity import Activity

# Placeholder namespace for the Fusion Energy Lexicon (FuEL), still in
# development. FuEL supplies the SKOS role concepts used as ``dcat:hadRole`` on a
# ``dcat:qualifiedRelation``, and as ``prov:hadRole`` on qualified usages and
# associations. Swap this single constant for the canonical FuEL URI once it is
# published.
FUEL_NAMESPACE = "https://w3id.org/fuel/ns#"

# FuEL role concepts marking a qualified relation's reference kind.
FUEL_GEOMETRY_ROLE = "fuel:geometry"
FUEL_CALIBRATION_ROLE = "fuel:calibration"
FUEL_ANNOTATION_ROLE = "fuel:annotation"

# FuEL role concepts qualifying a prov:Usage: how the activity used the entity.
FUEL_INPUT_ROLE = "fuel:input"
FUEL_INSTRUMENT_ROLE = "fuel:instrument"

# FuEL role concepts qualifying a prov:Association: the agent's function in the run.
FUEL_EXECUTOR_ROLE = "fuel:executor"
FUEL_ORCHESTRATOR_ROLE = "fuel:orchestrator"

_FUEL_ROLE_BY_AGENT_ROLE = {
    AgentRole.EXECUTOR: FUEL_EXECUTOR_ROLE,
    AgentRole.ORCHESTRATOR: FUEL_ORCHESTRATOR_ROLE,
}

_AGENT_TYPE_BY_KIND = {
    SourceKind.SOFTWARE: "prov:SoftwareAgent",
    SourceKind.PERSON: "prov:Person",
    SourceKind.ORGANIZATION: "prov:Organization",
}

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


def _build_used(activity: "Activity", base_url: str) -> tuple[list[Any], list[Any]]:
    """Build the ``prov:used`` shortcut list and ``prov:qualifiedUsage`` detail.

    Two kinds of used entity:
    - input datasets → ``prov:hadRole = fuel:input``
    - instruments (Sources of kind=instrument) → ``prov:hadRole = fuel:instrument``

    Returns ``(used, qualified_usage)``. ``used`` is the plain shortcut list of
    entity references; ``qualified_usage`` carries the role on each.
    """
    entries: list[tuple[str, str]] = []  # (entity @id, FuEL role concept)
    for ds in getattr(activity, "input_datasets", None) or []:
        entries.append((f"{base_url}/api/v1/datasets/{ds.id}", FUEL_INPUT_ROLE))
    for instrument in getattr(activity, "instruments", None) or []:
        entries.append(
            (f"{base_url}/api/v1/sources/{instrument.id}", FUEL_INSTRUMENT_ROLE)
        )

    used = [{"@id": uri, "@type": "prov:Entity"} for uri, _ in entries]
    qualified_usage = [
        {
            "@type": "prov:Usage",
            "prov:entity": {"@id": uri, "@type": "prov:Entity"},
            "prov:hadRole": {"@id": role},
        }
        for uri, role in entries
    ]
    return used, qualified_usage


def _agent_node(
    source: "Source",
    base_url: str,
    version: str | None = None,
    acted_on_behalf_of: list[str] | None = None,
) -> dict[str, Any]:
    """Build a PROV-O agent node for a Source, typed by its kind.

    ``acted_on_behalf_of`` is the list of agent URIs this agent acted on behalf of
    within the activity, emitted as ``prov:actedOnBehalfOf`` when present.
    """
    agent_type = _AGENT_TYPE_BY_KIND[source.kind]
    node: dict[str, Any] = {
        "@id": f"{base_url}/api/v1/sources/{source.id}",
        "@type": agent_type,
        "dct:title": source.name,
        "dct:description": source.description,
    }
    if version:
        node["dcat:version"] = version
    if acted_on_behalf_of:
        node["prov:actedOnBehalfOf"] = [{"@id": uri} for uri in acted_on_behalf_of]
    return {k: v for k, v in node.items() if v is not None}


def _build_associations(
    activity: "Activity", base_url: str
) -> tuple[dict[str, Any] | None, list[Any]]:
    """Build the executor ``prov:wasAssociatedWith`` node and the full
    ``prov:qualifiedAssociation`` list (executor + additional roled agents),
    threading ``prov:actedOnBehalfOf`` onto any agent that delegated.
    """
    # subordinate source id -> URIs of the agents it acted on behalf of
    behalf: dict[int, list[str]] = {}
    for link in getattr(activity, "delegation_links", None) or []:
        behalf.setdefault(link.subordinate_source_id, []).append(
            f"{base_url}/api/v1/sources/{link.responsible_source_id}"
        )

    primary: dict[str, Any] | None = None
    qualified: list[Any] = []

    executor: Source | None = getattr(activity, "source", None)
    if executor is not None:
        primary = _agent_node(
            executor,
            base_url,
            activity.source_version,
            acted_on_behalf_of=behalf.get(executor.id) if executor.id else None,
        )
        qualified.append(
            {
                "@type": "prov:Association",
                "prov:agent": {"@id": primary["@id"]},
                "prov:hadRole": {"@id": FUEL_EXECUTOR_ROLE},
            }
        )

    for link in getattr(activity, "agent_links", None) or []:
        agent = getattr(link, "source", None)
        if agent is None:
            continue
        qualified.append(
            {
                "@type": "prov:Association",
                "prov:agent": _agent_node(
                    agent,
                    base_url,
                    acted_on_behalf_of=behalf.get(agent.id) if agent.id else None,
                ),
                "prov:hadRole": {"@id": _FUEL_ROLE_BY_AGENT_ROLE[link.role]},
            }
        )

    return primary, qualified


def _derivation_source_node(derivation: Any, base_url: str) -> dict[str, Any]:
    """Build the upstream ``prov:Entity`` of an asserted derivation.

    The upstream is identified as far as the producer could manage. A registered
    dataset resolves to its FDS URI; an identifier that is already a URI, or a
    bare DOI, becomes the ``@id``; any other identifier is carried as
    ``dct:identifier`` on a node with no ``@id``. An upstream that is only
    described is a blank node with just its title and description, which is
    honest about being unresolvable.
    """
    node: dict[str, Any] = {"@type": "prov:Entity"}

    if derivation.source_dataset_id is not None:
        node["@id"] = f"{base_url}/api/v1/datasets/{derivation.source_dataset_id}"
    elif derivation.source_identifier:
        uri = _as_uri(derivation.source_identifier)
        if uri:
            node["@id"] = uri
        else:
            node["dct:identifier"] = derivation.source_identifier

    if derivation.source_label:
        node["dct:title"] = derivation.source_label
    if derivation.source_description:
        node["dct:description"] = derivation.source_description
    return node


# Compact PID forms expanded to a resolvable URI, keyed by lowercase prefix. Each
# entry is a scheme with a single canonical resolver, so expanding it is a fact
# rather than a guess. ARK is deliberately absent: it has no canonical resolver
# host, only conventions, so FDS would be inventing one.
_PID_RESOLVERS = {
    "doi:": "https://doi.org/",
    "hdl:": "https://hdl.handle.net/",
    "swh:": "https://archive.softwareheritage.org/",
}

# Schemes that are already absolute IRIs and stand as an ``@id`` unchanged. An
# ``@id`` identifies; it need not dereference.
_BARE_URI_SCHEMES = ("urn:",)


def _as_uri(identifier: str) -> str | None:
    """Resolve an identifier to a URI usable as an ``@id``, or None if it is not one.

    Deliberately an allowlist rather than a general ``scheme:rest`` pattern: a
    permissive rule would promote a typo or an unregistered scheme to an ``@id``,
    asserting a resolvability FDS cannot back. Anything unrecognised is better
    recorded verbatim as ``dct:identifier``.
    """
    candidate = identifier.strip()
    if not candidate:
        return None
    if "://" in candidate:
        return candidate

    lowered = candidate.lower()
    if lowered.startswith(_BARE_URI_SCHEMES):
        return candidate
    for prefix, resolver in _PID_RESOLVERS.items():
        if lowered.startswith(prefix):
            # swh: keeps its scheme in the path; doi:/hdl: do not.
            suffix = candidate if prefix == "swh:" else candidate[len(prefix) :]
            return f"{resolver}{suffix}"
    # A bare DOI: the "10." prefix range belongs to DOI alone, so this is
    # unambiguous. Bare Handles are not, so they need the hdl: prefix.
    if candidate.startswith("10."):
        return f"https://doi.org/{candidate}"
    return None


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
    """Maps a Shot to a ``dcat:Catalog`` JSON-LD document.

    A shot holds no data itself. The data sits in the Datasets and Collections
    that carry its ``shot_id``. ``dcat:Dataset`` would promise something to download.
    ``dcat:Catalog`` is a kind of ``dcat:Dataset`` in DCAT 3, so every field set
    below is still allowed on it.

    This document does not list the shot's datasets. You find those by asking
    for datasets with that ``shot_id``, there can be any number of them, and the
    Device catalog does not list its contents either.
    """
    shot_uri = f"{base_url}/api/v1/devices/{shot.device_name}/shots/{shot.id}"
    data: dict[str, Any] = {
        "@context": METADATA_CONTEXT,
        "@type": "dcat:Catalog",
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
    activity: Activity | None = getattr(dataset, "activity", None)
    if activity:
        data["prov:wasGeneratedBy"] = _build_activity_node(activity, base_url)

    derivations = getattr(dataset, "derivations", None) or []
    if derivations:
        data["prov:wasDerivedFrom"] = [
            _derivation_source_node(d, base_url) for d in derivations
        ]
        if activity:
            activity_uri = f"{base_url}/api/v1/activities/{activity.id}"
            data["prov:qualifiedDerivation"] = [
                {
                    "@type": "prov:Derivation",
                    "prov:entity": _derivation_source_node(d, base_url),
                    "prov:hadActivity": {"@id": activity_uri},
                }
                for d in derivations
            ]

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


def _build_activity_node(activity: "Activity", base_url: str) -> dict[str, Any]:
    """Build the embedded ``prov:Activity`` node."""
    prov_node: dict[str, Any] = {
        "@type": "prov:Activity",
        "prov:type": activity.activity_type,
    }
    primary, qualified = _build_associations(activity, base_url)
    if primary:
        prov_node["prov:wasAssociatedWith"] = primary
    if qualified:
        prov_node["prov:qualifiedAssociation"] = qualified
    if activity.started_at:
        prov_node["prov:startedAtTime"] = activity.started_at.isoformat()
    if activity.ended_at:
        prov_node["prov:endedAtTime"] = activity.ended_at.isoformat()
    if activity.parameters:
        prov_node["prov:value"] = activity.parameters
    used, qualified_usage = _build_used(activity, base_url)
    if used:
        prov_node["prov:used"] = used
        prov_node["prov:qualifiedUsage"] = qualified_usage
    return prov_node


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
    """Maps a Collection to a JSON-LD document typed as both ``dcat:Catalog``
    and ``prov:Collection``.

    Member Datasets are serialised as ``dcat:dataset`` references and nested
    child Collections as ``dcat:catalog`` references (``@id`` plus title; the
    full documents live at their own URIs). Every member is additionally linked
    with ``prov:hadMember``, making the collection a well-formed
    ``prov:Collection``. The producing Activity, if present, is embedded as a
    ``prov:wasGeneratedBy`` node, consistent with ``map_dataset_to_dcat``.
    """
    collection_id = getattr(collection, "id", None)
    collection_uri = (
        f"{base_url}/api/v1/collections/{collection_id}" if collection_id else None
    )

    data: dict[str, Any] = {
        "@context": METADATA_CONTEXT,
        "@type": ["dcat:Catalog", "prov:Collection"],
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

    # Claims about what this collection is: a run's outputs where activity_id is
    # set, a selection's criteria otherwise. Same projection as Shot and Dataset.
    sci_meta = getattr(collection, "scientific_metadata", None)
    if sci_meta:
        data["schema:additionalProperty"] = _map_scientific_metadata_to_jsonld(sci_meta)

    # Collection root → dcat:distribution (DCAT 3: dcat:Catalog is a dcat:Dataset subclass)
    # root_url is the format-agnostic access root for all physical data in this collection.
    root_url: str | None = getattr(collection, "root_url", None)
    if root_url:
        data["dcat:distribution"] = {
            "@type": "dcat:Distribution",
            "dcat:accessURL": root_url,
        }

    # Members (Datasets and nested Collections) are serialised as DCAT
    # references and, in PROV terms, collected via prov:hadMember below.
    member_ids: list[str] = []

    member_datasets: list[Any] = getattr(collection, "datasets", []) or []
    dataset_refs = [
        {
            "@id": f"{base_url}/api/v1/datasets/{ds.id}",
            "@type": "dcat:Dataset",
            "dct:title": ds.title or ds.name,
        }
        for ds in member_datasets
        if getattr(ds, "id", None)
    ]
    if dataset_refs:
        data["dcat:dataset"] = dataset_refs
        member_ids.extend(ref["@id"] for ref in dataset_refs)

    child_collections: list[Any] = getattr(collection, "child_collections", []) or []
    catalog_refs = [
        {
            "@id": f"{base_url}/api/v1/collections/{c.id}",
            "@type": "dcat:Catalog",
            "dct:title": c.title or c.name,
        }
        for c in child_collections
        if getattr(c, "id", None)
    ]
    if catalog_refs:
        data["dcat:catalog"] = catalog_refs
        member_ids.extend(ref["@id"] for ref in catalog_refs)

    # PROV-O: link every member entity with prov:hadMember (prov:Collection).
    if member_ids:
        data["prov:hadMember"] = [{"@id": uri} for uri in member_ids]

    # PROV-O provenance: embed the producing Activity if present
    activity: Activity | None = getattr(collection, "activity", None)
    if activity:
        data["prov:wasGeneratedBy"] = _build_activity_node(activity, base_url)

    return {k: v for k, v in data.items() if v is not None}
