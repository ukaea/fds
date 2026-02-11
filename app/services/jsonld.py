from typing import Any

from app.models.dataset import Dataset, DatasetRead
from app.models.device import Device, DeviceRead

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
        "created": dataset.created_at.isoformat()
        if hasattr(dataset, "created_at")
        else None,
        "modified": dataset.updated_at.isoformat()
        if hasattr(dataset, "updated_at")
        else None,
        "keywords": dataset.keywords.split(",") if dataset.keywords else [],
        "license": dataset.license,
        "version": dataset.version,
        "mediaType": dataset.media_type,
        "format": dataset.format,
    }

    # Access Rights mapping
    if dataset.access_level:
        data["accessRights"] = dataset.access_level.value

    # PROV-O Mapping (Provenance)
    # Check if the dataset object has source_links loaded
    if hasattr(dataset, "source_links") and dataset.source_links:
        activities = []
        for link in dataset.source_links:
            # Source Entity URI
            source_uri = f"{base_url}/api/v1/sources/{link.source_id}"

            # Create an Activity for the generation
            activity = {
                "@type": "prov:Activity",
                "prov:type": link.activity_type,
                "prov:used": {
                    "@id": source_uri,
                    "@type": "prov:Entity",
                    "dct:title": link.source.name
                    if link.source
                    else f"Source {link.source_id}",
                    "dct:description": link.source.description if link.source else None,
                    "dcat:version": link.source_version,
                },
            }

            # Add parameters if they exist
            if link.parameters:
                # We can map parameters to a generic value or specific property
                # For now, let's just dump them as a value
                activity["prov:value"] = link.parameters

            activities.append(activity)

        if len(activities) == 1:
            data["prov:wasGeneratedBy"] = activities[0]
        elif len(activities) > 1:
            data["prov:wasGeneratedBy"] = activities

    return {k: v for k, v in data.items() if v is not None}
