import fnmatch
import hashlib
from typing import NotRequired, TypedDict, cast

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.auth.exceptions import create_unauthorized_exception
from app.auth.jwks import JWKSClientDep
from app.core.config import config
from app.core.context import set_actor
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


class TokenClaims(TypedDict):
    """Validated JWT claims consumed by the FDS auth layer.

    `iss` is required because issuer validation happens during token decoding and
    is used later for scope filtering and pseudonymous user ID generation.

    `scp` and `scope` are both supported to accommodate different IdP claim
    conventions. Either claim may be represented as a space-delimited string or
    a list of strings.
    """

    iss: str
    sub: NotRequired[str]
    scp: NotRequired[str | list[str]]
    scope: NotRequired[str | list[str]]


async def get_token_claims(
    jwks_client: JWKSClientDep,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenClaims | None:
    """
    Dependency that gets the bearer token, validates its signature, and
    returns the decoded claims. Returns None if no token provided.
    """
    if auth is None:
        return None

    try:
        key = await jwks_client.get_signing_key(auth.credentials)
        valid_issuers = [t.issuer for t in config.TRUSTED_IDPS]
        claims = jwt.decode(
            auth.credentials,
            key=key,
            algorithms=["RS256"],
            audience=config.OIDC_AUDIENCE,
            issuer=valid_issuers,
        )
        return cast(TokenClaims, claims)
    except (jwt.PyJWTError, ValidationError) as e:
        raise create_unauthorized_exception(
            detail=f"Invalid token: {e}",
            authenticate_header="Bearer",
        )


def _extract_scopes(claims: TokenClaims) -> list[str]:
    scope_claim: str | list[str] | None = claims.get("scp")
    if scope_claim is None:
        scope_claim = claims.get("scope", "")

    if isinstance(scope_claim, str):
        return scope_claim.split()
    if isinstance(scope_claim, list):
        return [str(item) for item in scope_claim]
    return []


def _filter_scopes(raw_scopes: list[str], issuer: str) -> tuple[str, ...]:
    trusted_idp = next((t for t in config.TRUSTED_IDPS if t.issuer == issuer), None)
    if not trusted_idp:
        return ()

    final_scopes: list[str] = []
    for scope in raw_scopes:
        if any(
            fnmatch.fnmatchcase(scope, pattern)
            for pattern in trusted_idp.allowed_scopes
        ):
            final_scopes.append(scope)
    return tuple(final_scopes)


def _hash_user_id(issuer: str, sub: str) -> str:
    composite_id = f"{issuer}|{sub}"
    return hashlib.sha256(composite_id.encode("utf-8")).hexdigest()


async def get_current_user(
    claims: TokenClaims | None = Depends(get_token_claims),
) -> AuthenticatedUser:
    """
    Dependency that takes decoded JWT claims and returns an AuthenticatedUser model.
    Applies scope filtering and PII hashing.
    """
    if not claims:
        set_actor(ANONYMOUS_USER)
        return ANONYMOUS_USER

    raw_scopes = _extract_scopes(claims)
    issuer = claims["iss"]
    subject = claims.get("sub", "")
    final_scopes = _filter_scopes(raw_scopes, issuer)
    hashed_id = _hash_user_id(issuer, subject)

    user = AuthenticatedUser(id=hashed_id, scopes=final_scopes, issuer=issuer)
    # Publishes the actor to every log line emitted for this request.
    set_actor(user)
    return user
