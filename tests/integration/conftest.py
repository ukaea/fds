"""
Integration test fixtures.

Requires the demo docker-compose stack to be running:
    docker-compose -f demo/docker-compose.yaml up -d

Run integration tests with:
    pytest -m integration
"""

from collections.abc import Generator

import httpx
import pytest

FDS_URL = "http://localhost:8000/api/v1"
KC_TOKEN_URL = "http://localhost:8080/realms/fds/protocol/openid-connect/token"
CLIENT_ID = "fds-client"
CLIENT_SECRET = "fds-client-secret"


def _get_token(username: str, password: str, scope: str = "openid profile") -> str:
    resp = httpx.post(
        KC_TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": username,
            "password": password,
            "grant_type": "password",
            "scope": scope,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers() -> dict[str, str]:
    token = _get_token("admin", "password", "openid profile fds-admin")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def user_headers() -> dict[str, str]:
    token = _get_token("user", "password")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def mast_admin_headers() -> dict[str, str]:
    token = _get_token("mast_admin", "password")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    with httpx.Client(timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def seeded_data(admin_headers: dict[str, str]) -> dict:
    from demo.seed_metadata import seed_all

    return seed_all(FDS_URL, admin_headers)
