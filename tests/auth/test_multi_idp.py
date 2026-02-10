import hashlib

import jwt
import pytest
from fastapi import HTTPException

from app.auth.security import get_current_user, get_token_claims
from app.core.config import TrustedIdP

# Mock Data
IDP_JET = "https://idp.jet.org"
IDP_MAST = "https://idp.mast.ac.uk"
IDP_ROGUE = "https://rogue-idp.com"


@pytest.fixture
def setup_trusted_idps(mocker):
    # Setup Trusted IdPs
    trusted_idps = [
        TrustedIdP(issuer=IDP_JET, allowed_scopes=["jet:*", "openid"]),
        TrustedIdP(issuer=IDP_MAST, allowed_scopes=["mast:*", "openid"]),
    ]
    # We use app.auth.security.config because that's where it's imported in the SUT
    from app.auth.security import config

    mocker.patch.object(config, "TRUSTED_IDPS", trusted_idps)
    return config


@pytest.mark.asyncio
async def test_get_token_claims_valid_idp(
    setup_trusted_idps, mock_jwks_client, mock_jwt_decode, mocker
):
    """Verify generic token acceptance from a trusted IdP"""
    token_claims = {"iss": IDP_JET, "sub": "user1", "scope": "openid jet:read"}
    mock_jwt_decode.return_value = token_claims

    mock_auth = mocker.Mock()
    mock_auth.credentials = "token"

    # Should succeed
    claims = await get_token_claims(jwks_client=mock_jwks_client, auth=mock_auth)
    assert claims == token_claims


@pytest.mark.asyncio
async def test_get_token_claims_untrusted_idp(
    setup_trusted_idps, mock_jwks_client, mock_jwt_decode, mocker
):
    """Verify rejection of untrusted IdP"""
    token_claims = {"iss": IDP_ROGUE, "sub": "hacker", "scope": "fds-admin"}

    # We need to simulate jwt.decode logic or let it run?
    # security.py calls jwt.decode with issuer=valid_issuers.
    # if we mock jwt.decode to just return claims, it WON'T validation the issuer.
    # We must configure the mock to raise InvalidIssuerError if the issuer in token doesn't match expected.

    def side_effect_decode(token, **kwargs):
        # Simulation of pyjwt issuer validation
        allowed_issuers = kwargs.get("issuer", [])
        if isinstance(allowed_issuers, str):
            allowed_issuers = [allowed_issuers]

        # Extract issuer from token (conceptually)
        if token_claims["iss"] not in allowed_issuers:
            raise jwt.InvalidIssuerError("Invalid issuer")
        return token_claims

    mock_jwt_decode.side_effect = side_effect_decode

    auth = mocker.Mock()
    auth.credentials = "token"

    with pytest.raises(HTTPException) as exc:
        await get_token_claims(jwks_client=mock_jwks_client, auth=auth)
    assert exc.value.status_code == 401
    # security.py wraps PyJWTError into "Invalid token: {e}"
    assert "Invalid token" in exc.value.detail
    assert "Invalid issuer" in exc.value.detail


@pytest.mark.asyncio
async def test_scope_filtering_stripped(setup_trusted_idps):
    """Verify unauthorized scopes are stripped based on IdP"""
    # IDP_JET is only allowed ["jet:*", "openid"]
    # Token has "mast:admin" which should be removed
    claims = {"iss": IDP_JET, "sub": "user1", "scope": "openid jet:read mast:admin"}

    user = await get_current_user(claims=claims)

    assert "jet:read" in user.scopes
    assert "openid" in user.scopes
    assert "mast:admin" not in user.scopes
    assert len(user.scopes) == 2


@pytest.mark.asyncio
async def test_scope_filtering_wildcard(setup_trusted_idps):
    """Verify wildcard matching"""
    # IDP_JET allowed "jet:*"
    claims = {
        "iss": IDP_JET,
        "sub": "user1",
        "scope": "jet:write jet:read custom:scope",
    }
    user = await get_current_user(claims=claims)

    assert "jet:write" in user.scopes
    assert "jet:read" in user.scopes
    assert "custom:scope" not in user.scopes


@pytest.mark.asyncio
async def test_pii_hashing(setup_trusted_idps):
    """Verify user ID is hashed and namespaced"""
    claims = {"iss": IDP_JET, "sub": "user_123", "scope": "openid"}

    user = await get_current_user(claims=claims)

    expected_raw = f"{IDP_JET}|user_123"
    expected_hash = hashlib.sha256(expected_raw.encode()).hexdigest()

    assert user.id == expected_hash
    assert "user_123" not in user.id  # Original ID obscured
