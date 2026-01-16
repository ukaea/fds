import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError

from app.auth.exceptions import create_unauthorized_exception
from app.auth.jwks import JWKSClientDep
from app.core.config import config
from app.models.user import AuthenticatedUser

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_token_claims(
    jwks_client: JWKSClientDep,
    auth: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """
    Dependency that gets the bearer token, validates its signature, and
    returns the decoded claims. This is the "hard" part that requires mocking
    in tests.
    """
    if auth is None:
        raise create_unauthorized_exception(authenticate_header="Bearer")

    try:
        key = await jwks_client.get_signing_key(auth.credentials)
        issuer = f"{config.OIDC_PROTOCOL}://{config.OIDC_DOMAIN}"
        return jwt.decode(
            auth.credentials,
            key=key,
            algorithms=["RS256"],
            audience=config.OIDC_AUDIENCE,
            issuer=issuer,
        )
    except (jwt.PyJWTError, ValidationError) as e:
        raise create_unauthorized_exception(
            detail=f"Invalid token: {e}",
            authenticate_header="Bearer",
        )


async def get_current_user(
    claims: dict = Depends(get_token_claims),
) -> AuthenticatedUser:
    """
    Dependency that takes decoded JWT claims and returns an AuthenticatedUser model.
    This is a simple transformation and easy to test.
    """
    token_scopes_str = claims.get("scp", claims.get("scope", ""))
    if isinstance(token_scopes_str, str):
        scopes = token_scopes_str.split()
    else:
        scopes = list(token_scopes_str)  # Assume it's an iterable if not string

    return AuthenticatedUser(id=claims.get("sub", ""), scopes=scopes)
