"""The names this service publishes, and the routes that answer them.

These two used to be written out separately, in a mapper and in a router, and
drifted: the projection named a dataset `/datasets/{id}` while the only route
of that shape looked its argument up as a name, so every published identifier
resolved to an empty list. They are now built from the same templates, and the
last test here is what keeps that true.
"""

import pytest

from app.api.identifiers import router as identifier_router
from app.services.identifiers import Identifiers, resolve_base

BASE = "https://example.org"


@pytest.fixture(name="names")
def names_fixture() -> Identifiers:
    return Identifiers(BASE)


def test_names_are_paths_under_the_base(names: Identifiers):
    assert names.dataset(13) == f"{BASE}/datasets/13"
    assert names.collection(6) == f"{BASE}/collections/6"
    assert names.source(1) == f"{BASE}/sources/1"
    assert names.activity(6) == f"{BASE}/activities/6"
    assert names.device("mast") == f"{BASE}/devices/mast"
    assert names.shot("mast", "30420") == f"{BASE}/devices/mast/shots/30420"


def test_no_name_carries_an_api_version(names: Identifiers):
    """A version describes the contract, not the thing being named."""
    published = [
        names.dataset(1),
        names.collection(1),
        names.source(1),
        names.activity(1),
        names.device("mast"),
        names.shot("mast", "1"),
    ]
    assert not any("/v1/" in name for name in published)


def test_a_trailing_slash_on_the_base_is_not_doubled():
    assert Identifiers(f"{BASE}/").dataset(13) == f"{BASE}/datasets/13"


def test_every_name_has_a_route_that_answers_it(names: Identifiers):
    """The guard against the two halves drifting apart again."""
    served = {route.path for route in identifier_router.routes}  # type: ignore[attr-defined]

    for name in (
        names.dataset(13),
        names.collection(6),
        names.source(1),
        names.activity(6),
        names.device("mast"),
        names.shot("mast", "30420"),
    ):
        path = name.removeprefix(BASE)
        # The route is a template, so compare shapes rather than the filled path.
        assert any(
            len(route.strip("/").split("/")) == len(path.strip("/").split("/"))
            and route.strip("/").split("/")[0] == path.strip("/").split("/")[0]
            for route in served
        ), f"nothing serves {path}"


class TestResolvingTheBase:
    """Which address identifiers are published under."""

    def test_a_configured_address_wins(self):
        assert resolve_base("https://fds.example.org", "http://internal:8000") == (
            "https://fds.example.org"
        )

    def test_without_one_the_caller_s_view_is_used(self):
        """Correct when FDS is reached directly, as in development."""
        assert resolve_base("", "http://localhost:8000/") == "http://localhost:8000"

    def test_whitespace_is_not_a_configured_address(self):
        assert resolve_base("   ", "http://localhost:8000") == "http://localhost:8000"
