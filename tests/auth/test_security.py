import hashlib

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from fds.auth.security import (
    TokenClaims,
    _extract_roles,
    _filter_roles,
    _hash_user_id,
    get_current_user,
    get_token_claims,
)
from fds.core.config import TrustedIdP, config


@pytest.mark.asyncio
async def test_get_token_claims_success(mock_jwks_client, mock_jwt_decode):
    token = "valid_token"
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    expected_claims = {
        "sub": "user123",
        "scope": "read write",
        "iss": "https://test-idp.com",
    }
    mock_jwt_decode.return_value = expected_claims

    # Rely on conftest.py's mock_config to set TRUSTED_IDPS and OIDC_AUDIENCE
    # Default is issuer="https://test-idp.com", allowed_roles=["*"]

    claims = await get_token_claims(jwks_client=mock_jwks_client, auth=auth)
    assert claims == expected_claims
    mock_jwks_client.get_signing_key.assert_awaited_once_with(token)

    mock_jwt_decode.assert_called_once_with(
        token,
        key="mock_public_key",
        algorithms=["RS256"],
        audience="test-audience",
        issuer=["https://test-idp.com"],
    )


@pytest.mark.asyncio
async def test_get_token_claims_no_auth(mock_jwks_client):
    result = await get_token_claims(jwks_client=mock_jwks_client, auth=None)
    assert result is None


@pytest.mark.asyncio
async def test_get_token_claims_invalid_token(mock_jwks_client, mock_jwt_decode):
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad_token")
    mock_jwt_decode.side_effect = jwt.PyJWTError("Decode failed")

    with pytest.raises(HTTPException) as exc:
        await get_token_claims(jwks_client=mock_jwks_client, auth=auth)

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_parsing(mocker):
    # Override global config for this specific test case if needed,
    # but we can use the default "test-domain.com" from fixture to avoid patching.
    # However, to keep assertions stable with pre-calculated hashes, let's just
    # use the values we expect or update expectation.
    # The assertions expect "test-idp|..."

    # We need to mock config to ensure "iss" matches a trusted IDP
    # If no trusted IDP matches, roles are STRIPPED.

    trusted_idps = [TrustedIdP(issuer="test-idp", allowed_roles=["*"])]
    mocker.patch("fds.auth.security.config.TRUSTED_IDPS", trusted_idps)

    # Case 1: scope is string
    claims: TokenClaims = {"sub": "123", "scope": "A B", "iss": "test-idp"}
    user = await get_current_user(claims=claims)

    expected_id = hashlib.sha256(b"test-idp|123").hexdigest()
    assert user.id == expected_id
    assert user.roles == ("A", "B")

    # Case 2: use 'scp' instead of 'scope', list format
    claims_scp: TokenClaims = {"sub": "456", "scp": ["C", "D"], "iss": "test-idp"}
    user2 = await get_current_user(claims=claims_scp)

    expected_id2 = hashlib.sha256(b"test-idp|456").hexdigest()
    assert user2.id == expected_id2
    assert user2.roles == ("C", "D")

    # Case 3: No roles
    claims_none: TokenClaims = {"sub": "789", "iss": "test-idp"}
    user3 = await get_current_user(claims=claims_none)

    expected_id3 = hashlib.sha256(b"test-idp|789").hexdigest()
    assert user3.id == expected_id3
    assert user3.roles == ()


def test_extract_roles_string():
    claims: TokenClaims = {"iss": "https://test-idp.com", "scope": "read write delete"}
    assert _extract_roles(claims) == ["read", "write", "delete"]


def test_extract_roles_list():
    claims: TokenClaims = {"iss": "https://test-idp.com", "scope": ["read", "write"]}
    assert _extract_roles(claims) == ["read", "write"]


def test_extract_roles_scp_claim():
    claims: TokenClaims = {"iss": "https://test-idp.com", "scp": "admin"}
    assert _extract_roles(claims) == ["admin"]


def test_extract_roles_empty():
    assert _extract_roles({"iss": "https://test-idp.com"}) == []


def test_extract_roles_merges_entra_roles():
    claims: TokenClaims = {
        "iss": "https://test-idp.com",
        "scp": "read fds-admin",
        "roles": ["fds-admin", "mast-write"],
    }
    assert _extract_roles(claims) == ["read", "fds-admin", "mast-write"]


def test_extract_roles_roles_only():
    """Entra ID app-only tokens carry `roles` and no `scp`."""
    claims: TokenClaims = {"iss": "https://test-idp.com", "roles": ["fds-admin"]}
    assert _extract_roles(claims) == ["fds-admin"]


def test_hash_user_id():
    # Expected: SHA256("issuer|sub")
    issuer = "https://idp.com"
    sub = "user123"
    expected = hashlib.sha256(f"{issuer}|{sub}".encode()).hexdigest()
    assert _hash_user_id(issuer, sub) == expected


def test_hash_user_id_empty():
    expected = hashlib.sha256(b"|").hexdigest()
    assert _hash_user_id("", "") == expected


def test_filter_roles_no_trusted_idp(mocker):
    # Setup NO trusted IdPs
    mocker.patch.object(config, "TRUSTED_IDPS", [])

    roles = ["read", "write"]
    # Should return empty because issuer is unknown
    assert _filter_roles(roles, "https://unknown.com") == ()


def test_filter_roles_match(mocker):
    # Setup Trusted IdP
    trusted = [TrustedIdP(issuer="https://trust.com", allowed_roles=["read", "write"])]
    mocker.patch.object(config, "TRUSTED_IDPS", trusted)

    roles = ["read", "write", "admin"]
    filtered = _filter_roles(roles, "https://trust.com")

    assert "read" in filtered
    assert "write" in filtered
    assert "admin" not in filtered


def test_filter_roles_none_when_allowed_roles_unset(mocker):
    trusted = [TrustedIdP(issuer="https://trust.com")]
    mocker.patch.object(config, "TRUSTED_IDPS", trusted)

    assert _filter_roles(["fds-admin", "mast:read"], "https://trust.com") == ()


def test_filter_roles_wildcard(mocker):
    # Setup Trusted IdP with wildcard
    trusted = [TrustedIdP(issuer="https://trust.com", allowed_roles=["jet:*"])]
    mocker.patch.object(config, "TRUSTED_IDPS", trusted)

    roles = ["jet:read", "jet:write", "other:read"]
    filtered = _filter_roles(roles, "https://trust.com")

    assert "jet:read" in filtered
    assert "jet:write" in filtered
    assert "other:read" not in filtered


def test_filter_roles_case_sensitivity(mocker):
    # Setup Trusted IdP with a role pattern
    trusted = [TrustedIdP(issuer="https://trust.com", allowed_roles=["jet:*"])]
    mocker.patch.object(config, "TRUSTED_IDPS", trusted)

    # Roles should be case-sensitive
    # "JET:READ" should NOT match "jet:*"
    roles = ["jet:read", "JET:READ"]
    filtered = _filter_roles(roles, "https://trust.com")

    assert "jet:read" in filtered
    assert "JET:READ" not in filtered
