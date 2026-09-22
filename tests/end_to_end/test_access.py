"""Tokens are verified, and access is enforced, by the running service."""

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.end_to_end.conftest import FDS_URL, sign

pytestmark = pytest.mark.end_to_end

PAYLOAD = {"name": "smoke-unauthorised", "description": "x", "type": "tokamak"}


def test_write_is_rejected_without_a_token(http_client: httpx.Client):
    response = http_client.post(f"{FDS_URL}/devices/", json=PAYLOAD)
    assert response.status_code in (401, 403)


def test_write_is_rejected_without_the_scope(http_client: httpx.Client, signing_key):
    """A token the service trusts, carrying no administrative scope."""
    if signing_key is None:
        pytest.skip("no signing key available")

    token = sign(signing_key, scope="openid")
    response = http_client.post(
        f"{FDS_URL}/devices/",
        headers={"Authorization": f"Bearer {token}"},
        json=PAYLOAD,
    )
    assert response.status_code == 403


def test_token_from_an_untrusted_issuer_is_rejected(http_client: httpx.Client):
    """Signed by a key the service has never heard of."""
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = sign(impostor, scope="fds-admin", issuer="urn:fds:not-trusted")

    response = http_client.post(
        f"{FDS_URL}/devices/",
        headers={"Authorization": f"Bearer {token}"},
        json=PAYLOAD,
    )
    assert response.status_code in (401, 403)


def test_restricted_metadata_is_hidden_from_anonymous_callers(
    http_client: httpx.Client, admin_headers: dict[str, str], device
):
    created = device(access_level="restricted")

    anonymous = http_client.get(f"{FDS_URL}/devices/{created['name']}")
    assert anonymous.status_code in (401, 403, 404)

    authenticated = http_client.get(
        f"{FDS_URL}/devices/{created['name']}", headers=admin_headers
    )
    assert authenticated.status_code == 200
