from collections.abc import Sequence

from fds.models.identity import AuthenticatedUser
from fds.services.exceptions import ForbiddenError


def holds_any(user: AuthenticatedUser, roles: Sequence[str] | None) -> bool:
    """Whether the user holds one of ``roles``.

    An empty list asks only that the user is signed in, and ``None`` names nobody.
    """
    if roles is None or user.is_anonymous:
        return False
    return not roles or any(role in user.roles for role in roles)


def role_refusal(roles: Sequence[str]) -> ForbiddenError:
    """The refusal naming the roles that would have let the user in."""
    names = list(dict.fromkeys(roles)) or ["fds-admin"]
    if len(names) == 1:
        return ForbiddenError(f"Not authorized, requires role: {names[0]}")
    return ForbiddenError(f"Not authorized, requires one of roles: {', '.join(names)}")


def check_is_admin(user: AuthenticatedUser) -> None:
    """
    Checks that the user holds fds-admin.
    Raises ForbiddenError if not authorized.
    """
    if not user.is_admin():
        raise role_refusal(["fds-admin"])


def check_write_roles(user: AuthenticatedUser, write_roles: list[str] | None) -> None:
    """Checks that the user may write a record whose write roles are ``write_roles``.

    ``fds-admin`` always may. Raises ForbiddenError if not authorized.
    """
    if user.is_admin() or holds_any(user, write_roles):
        return
    if write_roles == [] and user.is_anonymous:
        raise ForbiddenError("Authentication required for this resource")
    raise role_refusal(write_roles or [])


def check_sets_write_roles(
    user: AuthenticatedUser,
    requested: list[str] | None,
    current: list[str] | None = None,
) -> None:
    """Checks that the user may set a record's write roles to ``requested``.

    Only ``fds-admin`` may set them; sending the stored value back changes nothing
    and is allowed.
    """
    if requested != current:
        check_is_admin(user)
