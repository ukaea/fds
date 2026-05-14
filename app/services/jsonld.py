from typing import TYPE_CHECKING, Any

from app.models.collection import Collection, CollectionRead
from app.models.dataset import Dataset, DatasetRead
from app.models.device import Device, DeviceRead
from app.models.distribution import Distribution

if TYPE_CHECKING:
    from app.models.activity import Activity

METADATA_CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "title": "dct:title",
    "description": "dct:description",
    "publisher": "dct:publisher",
    "identifier": "dct:identifier",
    "created": {"@id": "dct:created", "@type": "xsd:dateTime"},
    "modified": {"@id": "dct:modified", "@type": "xsd:dateTime"},
    "temporal": {"@id": "dct:temporal", "@type": "xsd:dateTime"},
    "creator": "dct:creator",
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


def map_dataset_to_dcat(
    dataset: Dataset | DatasetRead, base_url: str
) -> dict[str, Any]:
    """
    Maps a Dataset to a dcat:Dataset.
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

    # Access Rights mapping
    if dataset.access_level:
        data["accessRights"] = dataset.access_level.value

    # DCAT Distribution mapping
    distributions: list[Distribution] = getattr(dataset, "distributions", []) or []
    if distributions:
        dist_nodes = []
        for dist in distributions:
            node: dict[str, Any] = {
                "@type": "dcat:Distribution",
                "dcat:downloadURL": dist.url,
            }
            if dist.media_type:
                node["dcat:mediaType"] = dist.media_type
            if dist.format:
                node["dct:format"] = dist.format
            if dist.access_level:
                node["dct:accessRights"] = dist.access_level.value
            dist_nodes.append(node)
        data["dcat:distribution"] = dist_nodes
        # Convenience shorthand: downloadURL of the default distribution
        default = next((d for d in distributions if d.default_distribution), None)
        if default:
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

    return {k: v for k, v in data.items() if v is not None}


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
