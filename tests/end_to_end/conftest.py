"""Fixtures for the end-to-end suite.

These tests drive a running FDS over HTTP and assert nothing about its
internals, so the same suite runs against a container in CI and against a real
deployment as its smoke test:

    FDS_URL=https://api.example.org/v1 uv run pytest -m end_to_end

They prove the pieces are wired together: the app starts, the database is
migrated, tokens are verified, responses are serialised, content negotiation
works. Behaviour is tested in process, where it is faster and can be examined
more closely.

A token is needed for the tests that write. Either supply one:

    FDS_TOKEN=<jwt>

or point at a private key whose public half the target trusts, which is what
the local stack is set up for (see the README):

    FDS_SIGNING_KEY=dev/local-issuer.key    # the default

Without either, the tests that write are skipped and the read-only ones still
run, so the suite is usable against a deployment where you hold no key.

Everything these tests create, they delete.
"""

import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization

FDS_URL = os.environ.get("FDS_URL", "http://localhost:8000/v1")
SIGNING_KEY = Path(os.environ.get("FDS_SIGNING_KEY", "dev/local-issuer.key"))
ISSUER = os.environ.get("FDS_TOKEN_ISSUER", "urn:fds:local")
AUDIENCE = os.environ.get("FDS_TOKEN_AUDIENCE", "fds-client")


def sign(key, *, scope: str, issuer: str = ISSUER, kid: str = "local-1") -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": "end-to-end-tests",
            "aud": AUDIENCE,
            "scope": scope,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture(scope="session")
def signing_key():
    """The private key the target trusts, or None when we hold none."""
    if not SIGNING_KEY.exists():
        return None
    return serialization.load_pem_private_key(SIGNING_KEY.read_bytes(), password=None)


@pytest.fixture(scope="session")
def admin_token(signing_key) -> str:
    supplied = os.environ.get("FDS_TOKEN")
    if supplied:
        return supplied
    if signing_key is None:
        pytest.skip(
            f"no token: set FDS_TOKEN, or FDS_SIGNING_KEY to a key the target "
            f"trusts (looked for {SIGNING_KEY})"
        )
    return sign(signing_key, scope="fds-admin")


@pytest.fixture(scope="session")
def admin_headers(admin_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    with httpx.Client(timeout=30.0) as client:
        yield client


@pytest.fixture
def device(http_client: httpx.Client, admin_headers: dict[str, str]):
    """A device that exists only for one test, removed afterwards.

    Named uniquely so a failed run cannot collide with the next one, and so
    these tests are safe to point at a deployment holding real data.
    """
    created: list[str] = []

    def make(access_level: str = "public") -> dict:
        name = f"smoke-{uuid.uuid4().hex[:10]}"
        response = http_client.post(
            f"{FDS_URL}/devices/",
            headers=admin_headers,
            json={
                "name": name,
                "description": "created by the end-to-end suite",
                "type": "tokamak",
                "access_level": access_level,
            },
        )
        assert response.status_code == 201, response.text
        created.append(name)
        return response.json()

    yield make

    for name in created:
        http_client.delete(f"{FDS_URL}/devices/{name}", headers=admin_headers)
