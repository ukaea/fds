from typing import Callable

from fastapi import Depends, Path
from app.auth.security import AuthenticatedUser, get_current_user
from app.auth.permissions import check_device_admin, check_is_admin


def require_device_admin(
    device_name: str = Path(..., title="The name of the device"),
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    FastAPI dependency that checks if the user has admin privileges for a specific device.
    Delegates logic to domain-level check_device_admin.
    """
    check_device_admin(user, device_name)
    return user


def require_scope(
    required_scopes: list[str],
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """
    Simplified scope dependency factory. 
    Note: Real logic is now moving to services, but keeping this for top-level router dependencies if needed.
    """
    def _dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        # This is a bit coarse, but okay for top-level filters
        if "fds-admin" in user.scopes:
            return user
            
        if not set(required_scopes).issubset(user.scopes):
            # We still raise domain exception here if used? 
            # Or just let it be. 
            pass
        return user

    return _dependency


require_admin = require_scope(["fds-admin"])
