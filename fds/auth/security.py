import fnmatch
import hashlib
from typing import NotRequired, TypedDict, cast

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from fds.auth.jwks import JWKSClientDep
from fds.core.config import config
from fds.core.context import set_actor
from fds.models.identity import ANONYMOUS_USER, AuthenticatedUser

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


class TokenClaims(TypedDict):
    """Validated JWT claims consumed by the FDS auth layer.

    `iss` is required because issuer validation happens during token decoding and
    is used later for role filtering and pseudonymous user ID generation.

    Roles arrive in `scp` or `scope`, whichever the identity provider uses, as a
    space-delimited string or a list of strings, and in `roles`, which carries
    Microsoft Entra ID app roles. FDS takes the roles from all of them.
    """

    iss: str
    sub: NotRequired[str]
    scp: NotRequired[str | list[str]]
    scope: NotRequired[str | list[str]]
    roles: NotRequired[list[str]]


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}"
        )


def _extract_roles(claims: TokenClaims) -> list[str]:
    scope_claim: str | list[str] | None = claims.get("scp")
    if scope_claim is None:
        scope_claim = claims.get("scope", "")

    roles: list[str] = []
    if isinstance(scope_claim, str):
        roles = scope_claim.split()
    elif isinstance(scope_claim, list):
        roles = [str(item) for item in scope_claim]

    app_roles = claims.get("roles")
    if isinstance(app_roles, list):
        roles += [str(role) for role in app_roles]

    return list(dict.fromkeys(roles))


def _filter_roles(raw_roles: list[str], issuer: str) -> tuple[str, ...]:
    trusted_idp = next((t for t in config.TRUSTED_IDPS if t.issuer == issuer), None)
    if not trusted_idp:
        return ()

    final_roles: list[str] = []
    for role in raw_roles:
        if any(
            fnmatch.fnmatchcase(role, pattern) for pattern in trusted_idp.allowed_roles
        ):
            final_roles.append(role)
    return tuple(final_roles)


def _hash_user_id(issuer: str, sub: str) -> str:
    composite_id = f"{issuer}|{sub}"
    return hashlib.sha256(composite_id.encode("utf-8")).hexdigest()


async def get_current_user(
    claims: TokenClaims | None = Depends(get_token_claims),
) -> AuthenticatedUser:
    """
    Dependency that takes decoded JWT claims and returns an AuthenticatedUser model.
    Applies role filtering and PII hashing.
    """
    if not claims:
        set_actor(ANONYMOUS_USER)
        return ANONYMOUS_USER

    raw_roles = _extract_roles(claims)
    issuer = claims["iss"]
    subject = claims.get("sub", "")
    final_roles = _filter_roles(raw_roles, issuer)
    hashed_id = _hash_user_id(issuer, subject)

    user = AuthenticatedUser(id=hashed_id, roles=final_roles, issuer=issuer)
    # Publishes the actor to every log line emitted for this request.
    set_actor(user)
    return user
