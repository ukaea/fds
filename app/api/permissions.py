from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Path, status

from app.auth.security import AuthenticatedUser, get_current_user


def get_device_name(device_name: str = Path(...)) -> str:
    """
    Extract device_name from the path. 
    Using a dependency for this allows it to be composed easily.
    """
    return device_name


def require_device_admin(
    user: AuthenticatedUser = Depends(get_current_user),
    device_name: str = Depends(get_device_name),
) -> AuthenticatedUser:
    """
    Check if the user has admin rights for the specific device in the path.
    Requires scope 'fds-admin' or 'shot-operator:{device_name}'.
    """
    # 1. Check for global admin
    if "fds-admin" in user.scopes:
        return user

    # 2. Check for specific device admin scope
    required_scope = f"shot-operator:{device_name}"
    if required_scope in user.scopes:
        return user

    # 3. Fail
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Not authorized. Requires '{required_scope}' or 'fds-admin' scope.",
    )


# Type alias for easy use in routers
DeviceAdminDep = Annotated[AuthenticatedUser, Depends(require_device_admin)]


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
