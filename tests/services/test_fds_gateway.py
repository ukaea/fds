import httpx
import pytest
from pyld import jsonld

from fds.models.activity import ActivityType
from fds.models.federation import DatasetQuery
from fds.services.fds_gateway import UnreadableAnswer, in_fds_context, search

MEMBER = "https://api.fds.example.org"
LD = {"content-type": "application/ld+json"}

# A member whose context writes Dublin Core as dcterms and calls the title
# "name", answering with a dataset, its catalogue record, and a term FDS does
# not know.
ANSWER = {
    "@context": {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dcterms": "http://purl.org/dc/terms/",
        "fuel": "https://w3id.org/fuel/ns#",
        "name": "dcterms:title",
    },
    "@graph": [
        {
            "@id": "https://fds.example.org/datasets/7",
            "@type": "dcat:Dataset",
            "name": "Kinetic profiles",
            "fuel:device": "mast",
            "fuel:shot": "30421",
            "https://example.org/ns#colour": "blue",
        },
        {
            "@id": "https://fds.example.org/datasets/7#record",
            "@type": "dcat:CatalogRecord",
        },
    ],
}


def shot_listing(request: httpx.Request) -> httpx.Response:
    if (
        request.url.path == "/v1/devices/mast/shots/30421/datasets"
        and request.url.params.get("activity_type") == "simulation"
        and request.headers["accept"] == "application/ld+json"
    ):
        return httpx.Response(200, json=ANSWER, headers=LD)
    return httpx.Response(404)


def filtered_device_listing(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/devices/mast/datasets" and sorted(
        request.url.params.multi_items()
    ) == [
        ("include_replaced", "true"),
        ("limit", "20"),
        ("name", "equilibrium"),
        ("offset", "40"),
        ("property", "confinement_mode:H-mode"),
        ("property", "disruption"),
        ("scope", "shot"),
        ("shot_id_prefix", "304"),
        ("shot_property", "heating:SS"),
        ("source", "jintrac"),
    ]:
        return httpx.Response(200, json=ANSWER, headers=LD)
    return httpx.Response(404)


def every_dataset(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/datasets":
        return httpx.Response(200, json=ANSWER, headers=LD)
    return httpx.Response(404)


def plain_json_listing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=[{"id": 7, "name": "profiles"}])


def test_in_fds_context_writes_each_record_with_fds_terms():
    (node,) = in_fds_context(ANSWER)

    assert node == {
        "@id": "https://fds.example.org/datasets/7",
        "@type": "dcat:Dataset",
        "title": "Kinetic profiles",
        "fuel:device": "mast",
        "fuel:shot": "30421",
        "https://example.org/ns#colour": "blue",
    }


def test_in_fds_context_fetches_no_context(monkeypatch: pytest.MonkeyPatch):
    # pyld fetches a context with its default loader unless told otherwise.
    monkeypatch.setattr(jsonld, "_default_document_loader", pytest.fail)

    with pytest.raises(UnreadableAnswer):
        in_fds_context(
            {
                "@context": "https://example.org/context.jsonld",
                "@id": "https://example.org/datasets/1",
                "@type": "dcat:Dataset",
            }
        )


def test_search_asks_for_the_shots_datasets_in_jsonld():
    client = httpx.Client(transport=httpx.MockTransport(shot_listing))
    query = DatasetQuery(
        device_name="mast",
        shot_id="30421",
        activity_type=ActivityType.SIMULATION,
        limit=100,
    )

    (node,) = search(client, MEMBER, query)

    assert node["@id"] == "https://fds.example.org/datasets/7"
    assert node["title"] == "Kinetic profiles"


def test_search_passes_on_the_listings_filters_and_paging():
    client = httpx.Client(transport=httpx.MockTransport(filtered_device_listing))
    query = DatasetQuery(
        device_name="mast",
        scope="shot",
        name="equilibrium",
        properties=["confinement_mode:H-mode", "disruption"],
        shot_properties=["heating:SS"],
        source="jintrac",
        shot_id_prefix="304",
        include_replaced=True,
        offset=40,
        limit=20,
    )

    (node,) = search(client, MEMBER, query)

    assert node["@id"] == "https://fds.example.org/datasets/7"


def test_search_without_a_device_asks_for_every_dataset():
    client = httpx.Client(transport=httpx.MockTransport(every_dataset))

    (node,) = search(client, MEMBER, DatasetQuery(limit=100))

    assert node["@id"] == "https://fds.example.org/datasets/7"


def test_search_reports_a_member_that_answers_in_plain_json():
    client = httpx.Client(transport=httpx.MockTransport(plain_json_listing))
    query = DatasetQuery(device_name="mast", shot_id="30421", limit=100)

    with pytest.raises(UnreadableAnswer):
        search(client, MEMBER, query)
