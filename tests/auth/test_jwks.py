import httpx
import jwt
import pytest
from fastapi import HTTPException
from httpx import Request, Response

from app.auth.jwks import JwksClient

MOCK_ISSUER = "https://test-idp.com"
MOCK_OIDC_DISCOVERY = {
    "issuer": MOCK_ISSUER,
    "jwks_uri": f"{MOCK_ISSUER}/.well-known/jwks.json",
}
MOCK_JWKS = {
    "keys": [
        {
            "kid": "kid1",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "n1",
            "e": "e1",
        },
        {
            "kid": "kid2",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "n2",
            "e": "e2",
        },
    ]
}


@pytest.fixture
def jwks_client_instance(mocker):
    client = JwksClient()
    return client


@pytest.fixture
def mock_httpx(monkeypatch):
    """Mocks httpx.AsyncClient.get for OIDC/JWKS"""

    async def mock_get(_, url, **kwargs):
        url = str(url)
        if url == f"{MOCK_ISSUER}/.well-known/openid-configuration":
            return Response(200, json=MOCK_OIDC_DISCOVERY, request=Request("GET", url))
        if url == f"{MOCK_ISSUER}/.well-known/jwks.json":
            return Response(200, json=MOCK_JWKS, request=Request("GET", url))
        raise ValueError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)


@pytest.mark.asyncio
async def test_discover_jwks_uri_success(jwks_client_instance, mock_httpx):
    uri = await jwks_client_instance._discover_jwks_uri(MOCK_ISSUER)
    assert uri == MOCK_OIDC_DISCOVERY["jwks_uri"]


@pytest.mark.asyncio
async def test_discover_jwks_uri_untrusted(jwks_client_instance):
    with pytest.raises(HTTPException) as exc:
        await jwks_client_instance._discover_jwks_uri("https://evil.com")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_jwks_success(jwks_client_instance, mock_httpx):
    jwks = await jwks_client_instance.get_jwks(MOCK_ISSUER)
    assert jwks == MOCK_JWKS
    assert jwks_client_instance.cache[MOCK_ISSUER] == MOCK_JWKS


@pytest.mark.asyncio
async def test_get_signing_key_success(jwks_client_instance, mock_httpx, monkeypatch):
    token = "header.payload.sig"

    # Mock JWT parts to avoid crypto
    monkeypatch.setattr(jwt, "get_unverified_header", lambda t: {"kid": "kid1"})
    # Decode MUST return issuer now
    monkeypatch.setattr(jwt, "decode", lambda t, **k: {"iss": MOCK_ISSUER})

    # Mock PyJWK to return a string key
    class MockPyJWK:
        def __init__(self, key_data):
            pass

        @property
        def key(self):
            return "public_key"

    monkeypatch.setattr(jwt, "PyJWK", MockPyJWK)

    key = await jwks_client_instance.get_signing_key(token)
    assert key == "public_key"


@pytest.mark.asyncio
async def test_get_signing_key_rotation(jwks_client_instance, mocker):
    token = "header.payload.sig"
    kid_new = "kid_new"

    mocker.patch("jwt.get_unverified_header", return_value={"kid": kid_new})
    mocker.patch("jwt.decode", return_value={"iss": MOCK_ISSUER})

    # Mock PyJWK class
    mock_pyjwk = mocker.Mock()
    mock_pyjwk.return_value.key = "new_public_key"
    mocker.patch("jwt.PyJWK", mock_pyjwk)

    # State: Cache has old keys
    jwks_client_instance.cache[MOCK_ISSUER] = MOCK_JWKS

    # Mock httpx client response sequence
    # First call: OIDC discovery (implicitly cached or mocked)
    # Second call: JWKS fetch with new key
    new_jwks = {
        "keys": MOCK_JWKS["keys"]
        + [{"kid": kid_new, "kty": "RSA", "n": "n3", "e": "e3"}]
    }

    # We mock the client.get method directly on the instance
    # Use side_effect for conditional responses based on URL (simple fake)
    async def mock_get_side_effect(url, **kwargs):
        url = str(url)
        request = httpx.Request("GET", url)
        if "openid-configuration" in url:
            return httpx.Response(200, json=MOCK_OIDC_DISCOVERY, request=request)
        if "jwks.json" in url:
            return httpx.Response(200, json=new_jwks, request=request)
        raise ValueError(f"Unexpected URL: {url}")

    # Use spy/mock on the persistent client instance
    mock_client_get = mocker.patch.object(
        jwks_client_instance.client, "get", side_effect=mock_get_side_effect
    )

    key = await jwks_client_instance.get_signing_key(token)

    assert key == "new_public_key"
    assert mock_client_get.call_count >= 1


@pytest.mark.asyncio
async def test_get_jwks_upstream_error(jwks_client_instance, monkeypatch):
    """Test that a 500 from the IdP raises a 502 Bad Gateway"""

    async def mock_get(*args, **kwargs):
        return httpx.Response(500, request=httpx.Request("GET", "url"))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(HTTPException) as exc:
        await jwks_client_instance.get_jwks(MOCK_ISSUER)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Identity Provider returned an error during discovery."


@pytest.mark.asyncio
async def test_get_jwks_network_error(jwks_client_instance, monkeypatch):
    """Test that a network error raises a 503 Service Unavailable"""

    async def mock_get(*args, **kwargs):
        raise httpx.RequestError("Network failure", request=httpx.Request("GET", "url"))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(HTTPException) as exc:
        await jwks_client_instance.get_jwks(MOCK_ISSUER)

    assert exc.value.status_code == 503
    assert (
        exc.value.detail == "Failed to connect to Identity Provider during discovery."
    )
