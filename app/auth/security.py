import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, SecurityScopes
from pydantic import BaseModel, ValidationError

from app.auth.exceptions import create_unauthorized_exception
from app.auth.jwks import jwks_client
from app.core.config import config

# This creates the security scheme. It simply looks for an
# 'Authorization: Bearer <token>' header.
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Placeholder for user data extracted from the JWT."""

    id: str
    scopes: list[str] = []


async def get_current_user(
    security_scopes: SecurityScopes,
    auth: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency to validate the bearer token and return the user.

    This uses PyJWT to decode the token, verify its signature, audience,
    issuer, and required scopes.
    """
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    if auth is None:
        raise create_unauthorized_exception(authenticate_header=authenticate_value)

    try:
        key = await jwks_client.get_signing_key(auth.credentials)

        # The issuer URL must match the 'iss' claim in the JWT exactly.
        # OIDC issuers often have a trailing slash.
        issuer = f"https://{config.OIDC_DOMAIN}/"

        claims = jwt.decode(
            auth.credentials,
            key=key,
            algorithms=["RS256"],
            audience=config.OIDC_AUDIENCE,
            issuer=issuer,
        )

        # Extract scopes from the token claims
        token_scopes_str = claims.get("scp", claims.get("scope", ""))
        if isinstance(token_scopes_str, str):
            token_scopes = set(token_scopes_str.split())
        else:
            token_scopes = set(
                token_scopes_str
            )  # Assume it's an iterable if not string

        required_scopes = set(security_scopes.scopes)

        # Check if the token has all the required scopes
        if not required_scopes.issubset(token_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized for the required scope",
            )

        # The 'sub' claim is the standard place for the user's unique ID.
        # We also pass the token_scopes to the AuthenticatedUser model.
        return AuthenticatedUser(id=claims["sub"], scopes=list(token_scopes))

    except (jwt.PyJWTError, ValidationError) as e:
        raise create_unauthorized_exception(
            detail=f"Invalid token: {e}",
            authenticate_header=authenticate_value,
        )
