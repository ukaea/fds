import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_federation_service
from app.core.config import FederationMember
from app.main import app
from app.services.federation_service import FederationService

FIRST = FederationMember(
    id="https://first.example.org",
    title="First FDS",
    kind="fds",
    url="https://api.first.example.org",
)
SECOND = FederationMember(
    id="https://second.example.org",
    title="Second FDS",
    kind="fds",
    url="https://api.second.example.org",
)

ANSWER = {
    "@context": {"dcat": "http://www.w3.org/ns/dcat#"},
    "@graph": [
        {
            "@id": "https://first.example.org/datasets/7",
            "@type": "dcat:Dataset",
            "http://purl.org/dc/terms/title": "Kinetic profiles",
        }
    ],
}
LD = {"content-type": "application/ld+json"}


def first_answers_second_fails(request: httpx.Request) -> httpx.Response:
    if request.url.host == "api.first.example.org":
        return httpx.Response(200, json=ANSWER, headers=LD)
    return httpx.Response(500, json={"detail": "Internal server error"})


def first_answers_second_times_out(request: httpx.Request) -> httpx.Response:
    if request.url.host == "api.first.example.org":
        return httpx.Response(200, json=ANSWER, headers=LD)
    raise httpx.ReadTimeout("timed out", request=request)


def simulations_on_shots_from_304(request: httpx.Request) -> httpx.Response:
    if (
        request.url.path == "/v1/devices/mast/datasets"
        and request.url.params.get("activity_type") == "simulation"
        and request.url.params.get("shot_id_prefix") == "304"
        and request.url.params.get_list("property") == ["confinement_mode:H-mode"]
        and "activity_id" not in request.url.params
    ):
        return httpx.Response(200, json=ANSWER, headers=LD)
    return httpx.Response(404)


def test_read_members(test_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_federation_service,
        lambda: FederationService([FIRST, SECOND], timeout=5),
    )

    response = test_client.get("/v1/federation/members")

    assert response.status_code == 200
    assert response.json() == [
        {"id": "https://first.example.org", "title": "First FDS"},
        {"id": "https://second.example.org", "title": "Second FDS"},
    ]


def test_search_reports_each_members_answer_in_order(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_federation_service,
        lambda: FederationService(
            [FIRST, SECOND],
            timeout=5,
            transport=httpx.MockTransport(first_answers_second_fails),
        ),
    )

    response = test_client.get("/v1/federation/devices/mast/shots/30421/datasets")

    assert response.status_code == 200
    body = response.json()
    assert "dcat" in body["@context"]
    first, second = body["answers"]
    assert first == {
        "member": {"id": "https://first.example.org", "title": "First FDS"},
        "status": "answered",
        "datasets": [
            {
                "@id": "https://first.example.org/datasets/7",
                "@type": "dcat:Dataset",
                "title": "Kinetic profiles",
            }
        ],
    }
    assert second == {
        "member": {"id": "https://second.example.org", "title": "Second FDS"},
        "status": "failed",
        "detail": "answered with HTTP 500",
        "datasets": [],
    }


def test_search_reports_a_member_that_does_not_answer_in_time(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_federation_service,
        lambda: FederationService(
            [FIRST, SECOND],
            timeout=5,
            transport=httpx.MockTransport(first_answers_second_times_out),
        ),
    )

    response = test_client.get("/v1/federation/datasets")

    assert response.status_code == 200
    first, second = response.json()["answers"]
    assert first["status"] == "answered"
    assert second["status"] == "failed"
    assert second["detail"] == "did not answer in time"


def test_search_passes_the_listings_filters_to_members(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_federation_service,
        lambda: FederationService(
            [FIRST],
            timeout=5,
            transport=httpx.MockTransport(simulations_on_shots_from_304),
        ),
    )

    response = test_client.get(
        "/v1/federation/devices/mast/datasets",
        params={
            "activity_type": "simulation",
            "shot_id_prefix": "304",
            "property": "confinement_mode:H-mode",
            # An Activity's id in this catalogue means nothing to a member, so
            # it is not passed on.
            "activity_id": "6",
        },
    )

    assert response.status_code == 200
    (answer,) = response.json()["answers"]
    assert answer["status"] == "answered"
    assert [d["@id"] for d in answer["datasets"]] == [
        "https://first.example.org/datasets/7"
    ]


def test_search_with_no_members_has_no_answers(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_federation_service,
        lambda: FederationService([], timeout=5),
    )

    response = test_client.get("/v1/federation/datasets")

    assert response.status_code == 200
    assert response.json()["answers"] == []
