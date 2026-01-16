import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.jwks import JwksClient
from app.auth.security import (
    get_current_user,
    get_token_claims,
)


@pytest.mark.asyncio
async def test_get_token_claims_success(mocker):
    mock_jwks_client = mocker.AsyncMock(spec=JwksClient)
    mock_jwks_client.get_signing_key.return_value = "mock_public_key"

    token = "valid_token"
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    mock_decode = mocker.patch("app.auth.security.jwt.decode")
    expected_claims = {"sub": "user123", "scope": "read write"}
    mock_decode.return_value = expected_claims
    claims = await get_token_claims(jwks_client=mock_jwks_client, auth=auth)
    assert claims == expected_claims
    mock_jwks_client.get_signing_key.assert_awaited_once_with(token)
    mock_decode.assert_called_once_with(
        token,
        key="mock_public_key",
        algorithms=["RS256"],
        audience="test-audience",
        issuer="https://test-domain.com/",
    )


@pytest.mark.asyncio
async def test_get_token_claims_no_auth(mocker):
    mock_jwks_client = mocker.AsyncMock(spec=JwksClient)

    with pytest.raises(HTTPException) as exc:
        await get_token_claims(jwks_client=mock_jwks_client, auth=None)

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_get_token_claims_invalid_token(mocker):
    mock_jwks_client = mocker.AsyncMock(spec=JwksClient)
    mock_jwks_client.get_signing_key.return_value = "key"
    auth = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad_token")

    mock_decode = mocker.patch("app.auth.security.jwt.decode")
    mock_decode.side_effect = jwt.PyJWTError("Decode failed")

    with pytest.raises(HTTPException) as exc:
        await get_token_claims(jwks_client=mock_jwks_client, auth=auth)

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Invalid token" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_parsing():
    # Case 1: scope is string
    claims = {"sub": "123", "scope": "A B"}
    user = await get_current_user(claims=claims)
    assert user.id == "123"
    assert user.scopes == ["A", "B"]

    # Case 2: use 'scp' instead of 'scope', list format
    claims_scp = {"sub": "456", "scp": ["C", "D"]}
    user2 = await get_current_user(claims=claims_scp)
    assert user2.id == "456"
    assert user2.scopes == ["C", "D"]

    # Case 3: No scopes
    claims_none = {"sub": "789"}
    user3 = await get_current_user(claims=claims_none)
    assert user3.id == "789"
    assert user3.scopes == []
