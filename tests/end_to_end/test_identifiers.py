"""Every identifier FDS publishes must resolve.

The `@id` values in the semantic projection are what other catalogues store,
what provenance links point at, and what a DOI would eventually resolve to. An
identifier that 404s, or that quietly answers with the wrong resource, is worse
than none: a consumer cannot tell it has been misled.

This walks a real JSON-LD response and dereferences every identifier under the
service's own base URL, so a new one cannot be added without a route to serve
it.
"""

from typing import Any

import httpx
import pytest

from tests.end_to_end.conftest import FDS_URL

pytestmark = pytest.mark.end_to_end

ROOT = FDS_URL.removesuffix("/v1")


def identifiers(node: Any, found: set[str] | None = None) -> set[str]:
    """Every "@id" anywhere in a JSON-LD document that names this service."""
    found = set() if found is None else found
    if isinstance(node, dict):
        value = node.get("@id")
        if isinstance(value, str) and value.startswith(ROOT):
            found.add(value)
        for child in node.values():
            identifiers(child, found)
    elif isinstance(node, list):
        for child in node:
            identifiers(child, found)
    return found


@pytest.fixture
def dataset_with_provenance(
    http_client: httpx.Client, admin_headers: dict[str, str], device
) -> dict:
    """A dataset carrying the relations that pull other entities into its JSON-LD."""
    created = device(access_level="public")
    name = created["name"]

    shot = http_client.post(
        f"{FDS_URL}/devices/{name}/shots",
        headers=admin_headers,
        json={"id": "1", "access_level": "public"},
    )
    assert shot.status_code == 201, shot.text

    source = http_client.post(
        f"{FDS_URL}/sources/",
        headers=admin_headers,
        json={"name": f"{name}-code", "kind": "software"},
    )
    assert source.status_code == 201, source.text

    activity = http_client.post(
        f"{FDS_URL}/activities/",
        headers=admin_headers,
        json={"source_id": source.json()["id"], "activity_type": "simulation"},
    )
    assert activity.status_code == 201, activity.text

    upstream = http_client.post(
        f"{FDS_URL}/devices/{name}/shots/1/datasets",
        headers=admin_headers,
        json={"name": "raw", "level": 0, "url": "s3://example/raw"},
    )
    assert upstream.status_code == 201, upstream.text

    derived = http_client.post(
        f"{FDS_URL}/devices/{name}/shots/1/datasets",
        headers=admin_headers,
        json={
            "name": "processed",
            "level": 1,
            "url": "s3://example/processed",
            "activity_id": activity.json()["id"],
            "derived_from": [{"source_dataset_id": upstream.json()["id"]}],
        },
    )
    assert derived.status_code == 201, derived.text
    return derived.json()


def test_every_published_identifier_resolves(
    http_client: httpx.Client, admin_headers: dict[str, str], dataset_with_provenance
):
    response = http_client.get(
        f"{FDS_URL}/datasets/id/{dataset_with_provenance['id']}",
        headers={**admin_headers, "Accept": "application/ld+json"},
    )
    assert response.status_code == 200

    published = identifiers(response.json())
    # The dataset, its activity, the source that ran it, and its upstream.
    assert len(published) >= 4, published
    # None of them names an API route: a version belongs to the contract, not
    # to the thing being named.
    assert not any("/v1/" in identifier for identifier in published), published

    for identifier in sorted(published):
        resolved = http_client.get(identifier, headers=admin_headers)
        assert resolved.status_code == 200, f"{identifier} -> {resolved.status_code}"
        body = resolved.json()
        # A name lookup answers with a list, and an empty one at that: the
        # identifier would look fine and name nothing.
        assert isinstance(body, dict), f"{identifier} did not resolve to one resource"
        assert resolved.headers["content-type"].startswith("application/ld+json")
        assert body["@id"] == identifier, "resolved to a different identifier"
