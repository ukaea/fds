from app.models.user import AuthenticatedUser
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


def check_shot_operator(user: AuthenticatedUser, device_name: str) -> None:
    """
    Checks if the user has shot operator privileges for a specific device.
    Raises ForbiddenError if not authorized.
    """
    user_scopes = set(user.scopes)

    # Global admin override
    if "fds-admin" in user_scopes:
        return

    # Device admin override (Device admins can operate shots)
    if f"{device_name.lower()}_admin" in user_scopes:
        return

    # granular scope check
    required_scope = f"shot-operator:{device_name}"
    if required_scope not in user_scopes:
        raise ForbiddenError(f"Not authorized, requires scope: {required_scope}")
