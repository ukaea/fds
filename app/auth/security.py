import fnmatch
import hashlib

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.auth.exceptions import create_unauthorized_exception
from app.auth.jwks import JWKSClientDep
from app.core.config import config
from app.models.identity import AuthenticatedUser

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_claims(
    jwks_client: JWKSClientDep,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
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
        return claims
    except (jwt.PyJWTError, ValidationError) as e:
        raise create_unauthorized_exception(
            detail=f"Invalid token: {e}",
            authenticate_header="Bearer",
        )


def _extract_scopes(claims: dict) -> list[str]:
    token_scopes_str = claims.get("scp", claims.get("scope", ""))
    if isinstance(token_scopes_str, str):
        return token_scopes_str.split()
    return list(token_scopes_str)


def _filter_scopes(raw_scopes: list[str], issuer: str) -> list[str]:
    trusted_idp = next((t for t in config.TRUSTED_IDPS if t.issuer == issuer), None)
    if not trusted_idp:
        return []

    final_scopes = []
    for scope in raw_scopes:
        if any(
            fnmatch.fnmatchcase(scope, pattern)
            for pattern in trusted_idp.allowed_scopes
        ):
            final_scopes.append(scope)
    return final_scopes


def _hash_user_id(issuer: str, sub: str) -> str:
    composite_id = f"{issuer}|{sub}"
    return hashlib.sha256(composite_id.encode("utf-8")).hexdigest()


async def get_current_user(
    claims: dict | None = Depends(get_token_claims),
) -> AuthenticatedUser:
    """
    Dependency that takes decoded JWT claims and returns an AuthenticatedUser model.
    Applies scope filtering and PII hashing.
    """
    if not claims:
        from app.models.identity import ANONYMOUS_USER

        return ANONYMOUS_USER

    raw_scopes = _extract_scopes(claims)
    issuer = claims.get("iss")
    final_scopes = _filter_scopes(raw_scopes, issuer)
    hashed_id = _hash_user_id(issuer, claims.get("sub", ""))

    return AuthenticatedUser(id=hashed_id, scopes=final_scopes)
