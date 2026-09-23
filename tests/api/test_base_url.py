"""Which address identifiers are published under, and the warning when it is guessed.

Guessing is correct when FDS is reached directly, which is how it is run in
development. Behind something that terminates TLS the guess is wrong and
nothing fails: the response is well-formed and the identifier inside it names
an address no caller used. The warning exists because that is invisible
otherwise.
"""

from typing import ClassVar

import pytest

from app.api.base_url import _warn_about_guessing, get_base_url
from app.core.config import config


@pytest.fixture(autouse=True)
def _forget_previous_warnings():
    """The warning fires once per distinct answer; each test needs a fresh one."""
    _warn_about_guessing.cache_clear()


def test_direct_request_is_named_after_itself(test_client, log_lines):
    """Development: nothing in front, so the caller's view is the right answer."""
    response = test_client.get(
        "/devices/mast", headers={"Accept": "application/ld+json"}
    )

    assert response.status_code in (200, 404)
    assert not [line for line in log_lines() if "base_guessed" in line.get("event", "")]


def test_untrusted_forwarded_request_warns(test_client, log_lines):
    """A proxy said the request began as HTTPS, and we did not believe it."""
    test_client.get(
        "/devices/mast",
        headers={"Accept": "application/ld+json", "X-Forwarded-Proto": "https"},
    )

    (warning,) = [
        line for line in log_lines() if "base_guessed" in line.get("event", "")
    ]
    assert warning["level"] == "warning"
    assert "FDS_BASE_URL" in warning["detail"]
    assert warning["forwarded_proto"] == "https"


def test_the_warning_is_not_repeated(test_client, log_lines):
    for _ in range(3):
        test_client.get("/devices/mast", headers={"X-Forwarded-Proto": "https"})

    warnings = [line for line in log_lines() if "base_guessed" in line.get("event", "")]
    assert len(warnings) == 1


def test_a_configured_address_silences_the_guess(test_client, log_lines, monkeypatch):
    monkeypatch.setattr(config, "base_url", "https://fds.example.org")

    test_client.get("/devices/mast", headers={"X-Forwarded-Proto": "https"})

    assert not [line for line in log_lines() if "base_guessed" in line.get("event", "")]


def test_a_configured_address_is_what_identifiers_use(monkeypatch):
    monkeypatch.setattr(config, "base_url", "https://fds.example.org/")

    class Request:
        base_url = "http://internal:8000/"
        headers: ClassVar[dict[str, str]] = {}
        url = type("U", (), {"scheme": "http"})()

    assert get_base_url(Request()) == "https://fds.example.org"  # type: ignore[arg-type]


def test_every_route_publishes_the_same_name(test_client, monkeypatch, session):
    """The identifier route and the versioned API must agree.

    They did not: the versioned routes derived the base from the request while
    the identifier routes used the configured one, so with an address set the
    same dataset had two names depending on which route you asked. Nothing in
    the projection could have caught that, because each route was self
    consistent.
    """
    from app.auth.security import AuthenticatedUser
    from app.models.device import DeviceCreate
    from app.models.policy import AccessLevel
    from app.services.device_service import DeviceService

    monkeypatch.setattr(config, "base_url", "https://fds.example.org")
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    DeviceService(session).create(
        DeviceCreate(name="agree", type="tokamak", access_level=AccessLevel.PUBLIC),
        admin,
    )

    ld = {"Accept": "application/ld+json"}
    by_identifier = test_client.get("/devices/agree", headers=ld).json()
    by_api = test_client.get("/v1/devices/agree", headers=ld).json()

    assert by_identifier["@id"] == "https://fds.example.org/devices/agree"
    assert by_api["@id"] == by_identifier["@id"]
