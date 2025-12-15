import jwt
from typing import Annotated, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, ValidationError

from app.auth.exceptions import create_unauthorized_exception
from app.auth.jwks import JWKSClientDep
from app.core.config import config

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Placeholder for user data extracted from the JWT."""

    id: str
    scopes: list[str] = []


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
        issuer = f"https://{config.OIDC_DOMAIN}/"
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


async def get_current_user(claims: dict = Depends(get_token_claims)) -> AuthenticatedUser:
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


def require_scope(
    required_scopes: list[str],
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """
    A dependency factory that creates a dependency to check for required scopes.
    Includes an override for the 'fds-admin' scope, which grants all permissions.
    """

    def _dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        user_scopes = set(user.scopes)
        # The 'fds-admin' scope grants permission for any action.
        if "fds-admin" in user_scopes:
            return user

        if not set(required_scopes).issubset(user_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not authorized, requires scopes: {required_scopes}",
            )
        return user

    return _dependency


# Specific dependency that requires the 'fds-admin' scope.
require_admin = require_scope(["fds-admin"])


# Annotated type alias for admin dependency, can be used in function signatures.
AdminUserDep = Annotated[AuthenticatedUser, Depends(require_admin)]
