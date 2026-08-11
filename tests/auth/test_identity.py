import pytest

from app.auth.permissions import check_device_admin, check_is_admin, check_shot_operator
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.services.exceptions import ForbiddenError


def test_scopes_stored_as_tuple_when_given_list():
    """Pydantic must coerce a list of scopes into an immutable tuple."""
    user = AuthenticatedUser(id="u", scopes=("a:read", "b:write"))
    assert isinstance(user.scopes, tuple)
    assert user.scopes == ("a:read", "b:write")


def test_scopes_default_is_empty_tuple():
    user = AuthenticatedUser(id="u")
    assert user.scopes == ()
    assert isinstance(user.scopes, tuple)


def test_anonymous_user_scopes_are_empty_tuple():
    assert ANONYMOUS_USER.scopes == ()
    assert isinstance(ANONYMOUS_USER.scopes, tuple)


def test_scope_membership_hit():
    user = AuthenticatedUser(id="u", scopes=("read:data", "write:data"))
    assert "read:data" in user.scopes


def test_scope_membership_miss():
    user = AuthenticatedUser(id="u", scopes=("read:data",))
    assert "write:data" not in user.scopes


def test_scope_membership_empty():
    user = AuthenticatedUser(id="u", scopes=())
    assert "read:data" not in user.scopes


def test_is_admin_true():
    user = AuthenticatedUser(id="u", scopes=("fds-admin",))
    assert user.is_admin() is True


def test_is_admin_false_empty():
    user = AuthenticatedUser(id="u", scopes=())
    assert user.is_admin() is False


def test_is_admin_false_other_scopes():
    user = AuthenticatedUser(id="u", scopes=("read:public", "shot-operator:MAST"))
    assert user.is_admin() is False


def test_check_is_admin_passes():
    check_is_admin(AuthenticatedUser(id="u", scopes=("fds-admin",)))


def test_check_is_admin_raises():
    with pytest.raises(ForbiddenError, match="fds-admin"):
        check_is_admin(AuthenticatedUser(id="u", scopes=("other:scope",)))


def test_check_device_admin_via_global_admin():
    check_device_admin(AuthenticatedUser(id="u", scopes=("fds-admin",)), "MAST")


def test_check_device_admin_via_device_scope():
    check_device_admin(AuthenticatedUser(id="u", scopes=("mast_admin",)), "MAST")


def test_check_device_admin_raises():
    with pytest.raises(ForbiddenError):
        check_device_admin(AuthenticatedUser(id="u", scopes=("other:scope",)), "MAST")


def test_check_shot_operator_via_global_admin():
    check_shot_operator(AuthenticatedUser(id="u", scopes=("fds-admin",)), "MAST")


def test_check_shot_operator_via_device_admin():
    check_shot_operator(AuthenticatedUser(id="u", scopes=("mast_admin",)), "MAST")


def test_check_shot_operator_via_granular_scope():
    """Device-scoped grants are lower-cased, matching the ``{device}_admin`` form."""
    check_shot_operator(
        AuthenticatedUser(id="u", scopes=("shot-operator:mast",)), "MAST"
    )


def test_check_shot_operator_raises():
    with pytest.raises(ForbiddenError):
        check_shot_operator(AuthenticatedUser(id="u", scopes=("read:public",)), "MAST")
