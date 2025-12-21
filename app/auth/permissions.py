from app.auth.security import AuthenticatedUser
from app.services.exceptions import ForbiddenError


def check_device_admin(user: AuthenticatedUser, device_name: str) -> None:
    """
    Checks if the user has admin privileges for a specific device.
    Raises ForbiddenError if not authorized.
    """
    user_scopes = set(user.scopes)
    if "fds-admin" in user_scopes:
        return

    required_scope = f"{device_name.lower()}_admin"
    if required_scope not in user_scopes:
        raise ForbiddenError(f"Not authorized, requires scope: {required_scope}")


def check_is_admin(user: AuthenticatedUser) -> None:
    """
    Checks if the user has global admin privileges.
    Raises ForbiddenError if not authorized.
    """
    if "fds-admin" not in user.scopes:
        raise ForbiddenError("Not authorized, requires scope: fds-admin")
