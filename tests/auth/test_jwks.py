import httpx
import pytest
from fastapi import HTTPException
from httpx import Request, Response

from app.auth.jwks import JwksClient

# Mock data for OIDC discovery endpoint
MOCK_OIDC_DISCOVERY = {
    "issuer": "https://test-auth.com",
    "jwks_uri": "https://test-auth.com/.well-known/jwks.json",
    "authorization_endpoint": "https://test-auth.com/authorize",
    # ... other OIDC fields
}

# Mock data for JWKS endpoint
MOCK_JWKS = {
    "keys": [
        {
            "kid": "test-kid-1",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "some-n",
            "e": "some-e",
        },
        {
            "kid": "test-kid-2",
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": "some-other-n",
            "e": "some-other-e",
        },
    ]
}


# --- Fixtures and Setup ---
@pytest.fixture
def test_oidc_domain():
    return "test-auth.com"


@pytest.fixture
def jwks_client_instance(test_oidc_domain):
    """Provides a JwksClient instance for testing, ensuring clean state."""
    client = JwksClient(domain=test_oidc_domain)
    # Clear any potential lingering cache from other tests
    client.cache.clear()
    client.jwks_uri = ""
    client._jwks_uri_discovered = False
    return client


@pytest.fixture
def mock_httpx_get_discovery_success(monkeypatch, test_oidc_domain):
    """Mocks httpx.AsyncClient.get for successful OIDC discovery."""

    async def mock_get(_, url, **kwargs):
        url = str(url)  # Ensure URL is string for comparison
        expected_url = f"https://{test_oidc_domain}/.well-known/openid-configuration"
        if url == expected_url:
            return Response(200, json=MOCK_OIDC_DISCOVERY, request=Request("GET", url))
        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)


@pytest.fixture
def mock_httpx_get_jwks_success(monkeypatch, test_oidc_domain):
    """Mocks httpx.AsyncClient.get for successful JWKS fetching."""

    async def mock_get(_, url, **kwargs):
        url = str(url)
        expected_jwks_uri = f"https://{test_oidc_domain}/.well-known/jwks.json"
        if url == expected_jwks_uri:
            return Response(200, json=MOCK_JWKS, request=Request("GET", url))
        # Fallback for discovery if not already mocked
        expected_discovery_url = (
            f"https://{test_oidc_domain}/.well-known/openid-configuration"
        )
        if url == expected_discovery_url:
            return Response(200, json=MOCK_OIDC_DISCOVERY, request=Request("GET", url))
        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)


# --- Tests ---
@pytest.mark.asyncio
async def test_discover_jwks_uri_success(
    jwks_client_instance, mock_httpx_get_discovery_success
):
    """Test successful discovery of JWKS URI."""
    await jwks_client_instance._discover_jwks_uri()
    assert jwks_client_instance.jwks_uri == MOCK_OIDC_DISCOVERY["jwks_uri"]
    assert jwks_client_instance._jwks_uri_discovered is True


@pytest.mark.asyncio
async def test_discover_jwks_uri_no_domain(jwks_client_instance):
    """Test discovery fails if domain is not configured."""
    jwks_client_instance.domain = ""  # Clear domain for this test
    with pytest.raises(ValueError, match="OIDC_DOMAIN is not configured"):
        await jwks_client_instance._discover_jwks_uri()


@pytest.mark.asyncio
async def test_discover_jwks_uri_http_error(
    jwks_client_instance, monkeypatch, test_oidc_domain
):
    """Test discovery fails with an HTTP error from IdP."""

    async def mock_get_error(_, url, **kwargs):
        url = str(url)
        expected_url = f"https://{test_oidc_domain}/.well-known/openid-configuration"
        if url == expected_url:
            # Simulate a 500 error from the IdP
            return Response(
                500, request=Request("GET", url), text="Internal Server Error"
            )
        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_error)

    with pytest.raises(HTTPException) as exc_info:
        await jwks_client_instance._discover_jwks_uri()
    assert exc_info.value.status_code == 500
    assert "Error response 500" in exc_info.value.detail


@pytest.mark.asyncio
async def test_discover_jwks_uri_not_found_in_config(
    jwks_client_instance, monkeypatch, test_oidc_domain
):
    """Test discovery fails if jwks_uri is missing from OIDC config response."""

    async def mock_get_missing_jwks_uri(_, url, **kwargs):
        url = str(url)
        expected_url = f"https://{test_oidc_domain}/.well-known/openid-configuration"
        if url == expected_url:
            # Simulate response missing "jwks_uri"
            return Response(
                200,
                json={"issuer": "https://test-auth.com"},
                request=Request("GET", url),
            )
        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_missing_jwks_uri)

    with pytest.raises(HTTPException) as exc_info:
        await jwks_client_instance._discover_jwks_uri()
    assert exc_info.value.status_code == 500
    assert "JWKS URI not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_jwks_success(jwks_client_instance, mock_httpx_get_jwks_success):
    """Test successful fetching of JWKS."""
    jwks_client_instance.jwks_uri = MOCK_OIDC_DISCOVERY[
        "jwks_uri"
    ]  # Pre-set for direct test
    jwks = await jwks_client_instance.get_jwks()
    assert jwks == MOCK_JWKS
    assert jwks_client_instance.cache.get("jwks") == MOCK_JWKS


@pytest.mark.asyncio
async def test_get_jwks_from_cache(
    jwks_client_instance, mock_httpx_get_jwks_success, monkeypatch
):
    """Test that JWKS are retrieved from cache on subsequent calls."""
    # Ensure jwks_uri is discovered for get_jwks to proceed
    await jwks_client_instance._discover_jwks_uri()

    # Call get_jwks once to populate cache
    first_call_jwks = await jwks_client_instance.get_jwks()
    assert first_call_jwks == MOCK_JWKS

    # Now, clear the httpx mock to ensure no real HTTP calls are made
    monkeypatch.delattr(httpx.AsyncClient, "get")

    # Second call should retrieve from cache
    second_call_jwks = await jwks_client_instance.get_jwks()
    assert second_call_jwks == MOCK_JWKS

    # Verify that cache was used (no new HTTP call if mock deleted)
    # This test implicitly verifies cache usage by not raising an error
    # from a missing HTTP mock for the second call.


@pytest.mark.asyncio
async def test_get_jwks_http_error(jwks_client_instance, monkeypatch, test_oidc_domain):
    """Test fetching JWKS fails with an HTTP error."""
    jwks_client_instance.jwks_uri = MOCK_OIDC_DISCOVERY[
        "jwks_uri"
    ]  # Pre-set for direct test

    async def mock_get_error(_, url, **kwargs):
        url = str(url)
        expected_jwks_uri = f"https://{test_oidc_domain}/.well-known/jwks.json"
        if url == expected_jwks_uri:
            return Response(
                500, request=Request("GET", url), text="Internal Server Error"
            )
        # Fallback for discovery if not already mocked
        expected_discovery_url = (
            f"https://{test_oidc_domain}/.well-known/openid-configuration"
        )
        if url == expected_discovery_url:
            return Response(200, json=MOCK_OIDC_DISCOVERY, request=Request("GET", url))
        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_error)

    with pytest.raises(HTTPException) as exc_info:
        await jwks_client_instance.get_jwks()
    assert exc_info.value.status_code == 500
    assert "Error response 500" in exc_info.value.detail


# --- Key Rotation Tests ---


@pytest.mark.asyncio
async def test_get_signing_key_key_rotation(
    jwks_client_instance,
    mock_httpx_get_discovery_success,
    monkeypatch,
    test_oidc_domain,
):
    """
    Test that JwksClient refreshes the cache and retries if the signing key is not found
    (simulating key rotation).
    """
    import jwt

    # 1. Setup mocked token and header
    token = "header.payload.signature"
    kid_rotated = "test-kid-rotated-3"

    # Mock jwt.get_unverified_header to return our target kid
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda t: {"kid": kid_rotated, "alg": "RS256"}
    )

    # Mock jwt.PyJWK so we don't need real RSA keys
    class MockPyJWK:
        def __init__(self, key_data):
            self.key_data = key_data
            self.key = "public_key_string"  # what .key returns

    monkeypatch.setattr(jwt, "PyJWK", MockPyJWK)

    # 2. Setup HTTP mocks for Rotation

    MOCK_JWKS_ROTATED = {
        "keys": MOCK_JWKS["keys"]
        + [
            {
                "kid": kid_rotated,
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "new-n",
                "e": "new-e",
            }
        ]
    }

    # We need a closure to track call count across the async calls
    call_count = 0

    async def mock_get_rotation(_, url, **kwargs):
        nonlocal call_count
        url = str(url)

        # Discovery endpoint
        if url == f"https://{test_oidc_domain}/.well-known/openid-configuration":
            return Response(200, json=MOCK_OIDC_DISCOVERY, request=Request("GET", url))

        # JWKS endpoint
        if url == f"https://{test_oidc_domain}/.well-known/jwks.json":
            call_count += 1
            if call_count == 1:
                return Response(200, json=MOCK_JWKS, request=Request("GET", url))
            else:
                return Response(
                    200, json=MOCK_JWKS_ROTATED, request=Request("GET", url)
                )

        raise ValueError(f"Unexpected URL in mock: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_rotation)

    # 3. Execution
    # First ensure discovery happens
    await jwks_client_instance._discover_jwks_uri()

    # Populate cache with "stale" keys (Original MOCK_JWKS)
    await jwks_client_instance.get_jwks()
    assert call_count == 1

    # Now ask for the key that is ONLY in the rotated set
    # This should trigger:
    # 1. Look in cache -> Fail
    # 2. Clear cache
    # 3. Fetch JWKS (call_count becomes 2) -> Get MOCK_JWKS_ROTATED
    # 4. Find key -> Success

    key_str = await jwks_client_instance.get_signing_key(token)

    assert key_str == "public_key_string"
    assert call_count == 2
