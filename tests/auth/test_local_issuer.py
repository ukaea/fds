import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from pydantic import ValidationError

from app.auth.jwks import JwksClient
from app.auth.security import get_token_claims
from app.core.config import TrustedIdP

LOCAL_ISSUER = "urn:fds:local"
AUDIENCE = "fds-client"
KID = "local-1"


def _key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk |= {"kid": KID, "alg": "RS256", "use": "sig"}
    return private_key, {"keys": [jwk]}


@pytest.fixture(scope="module")
def key_pair():
    return _key_pair()


@pytest.fixture
def jwks_file(key_pair, tmp_path: Path) -> Path:
    _, jwks = key_pair
    path = tmp_path / "local-issuer.jwks.json"
    path.write_text(json.dumps(jwks))
    return path


def mint(
    private_key,
    *,
    issuer: str = LOCAL_ISSUER,
    audience: str = AUDIENCE,
    scope: str = "fds-admin",
    lifetime: timedelta = timedelta(minutes=15),
    kid: str = KID,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": issuer,
            "sub": "operator",
            "aud": audience,
            "scope": scope,
            "iat": now,
            "exp": now + lifetime,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


@pytest.fixture
def local_idp(mocker, jwks_file: Path):
    """Trust the local issuer, and fail loudly if anything tries the network."""
    from app.auth import security

    mocker.patch.object(
        security.config,
        "TRUSTED_IDPS",
        [TrustedIdP(issuer=LOCAL_ISSUER, jwks_file=jwks_file)],
    )
    mocker.patch.object(security.config, "OIDC_AUDIENCE", AUDIENCE)

    async def no_network(*_args, **_kwargs):
        raise AssertionError("a locally-keyed issuer must not be fetched over HTTP")

    mocker.patch.object(httpx.AsyncClient, "get", no_network)
    return JwksClient()


async def claims_for(client: JwksClient, token: str, mocker):
    auth = mocker.Mock()
    auth.credentials = token
    return await get_token_claims(jwks_client=client, auth=auth)


@pytest.mark.asyncio
async def test_minted_token_is_accepted(local_idp, key_pair, mocker):
    private_key, _ = key_pair
    claims = await claims_for(local_idp, mint(private_key), mocker)

    assert claims is not None
    assert claims["iss"] == LOCAL_ISSUER
    assert claims.get("sub") == "operator"
    assert claims.get("scope") == "fds-admin"


@pytest.mark.asyncio
async def test_token_signed_by_another_key_is_rejected(local_idp, mocker):
    """The whole point: only the holder of the private key can mint tokens."""
    impostor_key, _ = _key_pair()

    with pytest.raises(HTTPException) as exc:
        await claims_for(local_idp, mint(impostor_key), mocker)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_rejected(local_idp, key_pair, mocker):
    private_key, _ = key_pair
    expired = mint(private_key, lifetime=timedelta(minutes=-5))

    with pytest.raises(HTTPException) as exc:
        await claims_for(local_idp, expired, mocker)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_token_for_another_audience_is_rejected(local_idp, key_pair, mocker):
    private_key, _ = key_pair

    with pytest.raises(HTTPException) as exc:
        await claims_for(local_idp, mint(private_key, audience="someone-else"), mocker)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_token_from_an_untrusted_issuer_is_rejected(local_idp, key_pair, mocker):
    """Signed with the right key, but claiming an issuer that is not configured."""
    private_key, _ = key_pair

    with pytest.raises(HTTPException) as exc:
        await claims_for(local_idp, mint(private_key, issuer="urn:fds:other"), mocker)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_key_id_is_rejected(local_idp, key_pair, mocker):
    private_key, _ = key_pair

    with pytest.raises(HTTPException) as exc:
        await claims_for(local_idp, mint(private_key, kid="not-a-key"), mocker)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_rotating_the_file_is_picked_up_when_the_cache_expires(
    local_idp, key_pair, jwks_file, mocker
):
    """Replacing the key file revokes tokens minted with the old key."""
    private_key, _ = key_pair
    assert await claims_for(local_idp, mint(private_key), mocker) is not None

    new_key, new_jwks = _key_pair()
    jwks_file.write_text(json.dumps(new_jwks))
    local_idp.cache.clear()  # stands in for the TTL elapsing

    with pytest.raises(HTTPException):
        await claims_for(local_idp, mint(private_key), mocker)
    assert await claims_for(local_idp, mint(new_key), mocker) is not None


@pytest.mark.asyncio
async def test_missing_key_file_is_a_server_error(mocker, tmp_path, key_pair):
    """A deployment mistake, not something the caller did."""
    from app.auth import security

    private_key, _ = key_pair
    mocker.patch.object(
        security.config,
        "TRUSTED_IDPS",
        [TrustedIdP(issuer=LOCAL_ISSUER, jwks_file=tmp_path / "absent.json")],
    )
    mocker.patch.object(security.config, "OIDC_AUDIENCE", AUDIENCE)

    with pytest.raises(HTTPException) as exc:
        await claims_for(JwksClient(), mint(private_key), mocker)
    assert exc.value.status_code == 500


def test_jwks_uri_and_jwks_file_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValidationError, match="keys come from one place"):
        TrustedIdP(
            issuer=LOCAL_ISSUER,
            jwks_uri="https://idp.example.org/keys",
            jwks_file=tmp_path / "keys.json",
        )


@pytest.mark.asyncio
async def test_configured_jwks_uri_skips_discovery(mocker, key_pair):
    """The keys are fetched from the configured URI; discovery is never called."""
    private_key, jwks = key_pair
    issuer = "https://idp.example.org"
    keys_url = "http://idp-internal:8080/keys"

    from app.auth import security

    mocker.patch.object(
        security.config,
        "TRUSTED_IDPS",
        [TrustedIdP(issuer=issuer, jwks_uri=keys_url)],
    )
    mocker.patch.object(security.config, "OIDC_AUDIENCE", AUDIENCE)

    requested: list[str] = []

    async def fake_get(_self, url, **_kwargs):
        requested.append(str(url))
        return httpx.Response(200, json=jwks, request=httpx.Request("GET", str(url)))

    mocker.patch.object(httpx.AsyncClient, "get", fake_get)

    claims = await claims_for(JwksClient(), mint(private_key, issuer=issuer), mocker)

    assert claims is not None
    assert requested == [keys_url]
