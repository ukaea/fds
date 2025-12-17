from typing import Callable

from fastapi import Depends, HTTPException, status

from app.auth.security import AuthenticatedUser, get_current_user



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



require_admin = require_scope(["fds-admin"])
require_shot_admin = require_scope(["shot-admin"])
