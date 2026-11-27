import pytest

from fds.auth.permissions import (
    check_is_admin,
    check_sets_write_roles,
    check_write_roles,
    holds_any,
)
from fds.models.identity import ANONYMOUS_USER, AuthenticatedUser
from fds.services.exceptions import ForbiddenError


def test_roles_stored_as_tuple_when_given_list():
    """Pydantic must coerce a list of roles into an immutable tuple."""
    user = AuthenticatedUser(id="u", roles=("a:read", "b:write"))
    assert isinstance(user.roles, tuple)
    assert user.roles == ("a:read", "b:write")


def test_roles_default_is_empty_tuple():
    user = AuthenticatedUser(id="u")
    assert user.roles == ()
    assert isinstance(user.roles, tuple)


def test_anonymous_user_roles_are_empty_tuple():
    assert ANONYMOUS_USER.roles == ()
    assert isinstance(ANONYMOUS_USER.roles, tuple)


def test_role_membership_hit():
    user = AuthenticatedUser(id="u", roles=("read:data", "write:data"))
    assert "read:data" in user.roles


def test_role_membership_miss():
    user = AuthenticatedUser(id="u", roles=("read:data",))
    assert "write:data" not in user.roles


def test_role_membership_empty():
    user = AuthenticatedUser(id="u", roles=())
    assert "read:data" not in user.roles


def test_is_admin_true():
    user = AuthenticatedUser(id="u", roles=("fds-admin",))
    assert user.is_admin() is True


def test_is_admin_false_empty():
    user = AuthenticatedUser(id="u", roles=())
    assert user.is_admin() is False


def test_is_admin_false_other_roles():
    user = AuthenticatedUser(id="u", roles=("read:public", "mast-write"))
    assert user.is_admin() is False


def test_check_is_admin_passes():
    check_is_admin(AuthenticatedUser(id="u", roles=("fds-admin",)))


def test_check_is_admin_raises():
    with pytest.raises(ForbiddenError, match="fds-admin"):
        check_is_admin(AuthenticatedUser(id="u", roles=("other:role",)))


def test_holds_any_one_listed_role():
    user = AuthenticatedUser(id="u", roles=("jet-collab",))
    assert holds_any(user, ["mast-read", "jet-collab"])


def test_holds_any_refuses_an_unlisted_role():
    assert not holds_any(AuthenticatedUser(id="u", roles=("jet-read",)), ["mast-read"])


def test_holds_any_empty_list_needs_only_signing_in():
    assert holds_any(AuthenticatedUser(id="u"), [])
    assert not holds_any(ANONYMOUS_USER, [])


def test_holds_any_unset_list_names_nobody():
    assert not holds_any(AuthenticatedUser(id="u", roles=("mast-read",)), None)


def test_check_write_roles_passes_fds_admin_with_no_list():
    check_write_roles(AuthenticatedUser(id="u", roles=("fds-admin",)), None)


def test_check_write_roles_passes_a_listed_role():
    check_write_roles(AuthenticatedUser(id="u", roles=("mast-write",)), ["mast-write"])


def test_check_write_roles_names_the_roles_it_wanted():
    user = AuthenticatedUser(id="u", roles=("mast-read",))
    with pytest.raises(ForbiddenError, match="one of roles: mast-write, mast-ingest"):
        check_write_roles(user, ["mast-write", "mast-ingest"])


def test_check_write_roles_with_no_list_wants_fds_admin():
    user = AuthenticatedUser(id="u", roles=("mast-write",))
    with pytest.raises(ForbiddenError, match="requires role: fds-admin"):
        check_write_roles(user, None)


def test_check_sets_write_roles_refuses_a_writer():
    user = AuthenticatedUser(id="u", roles=("mast-write",))
    with pytest.raises(ForbiddenError, match="fds-admin"):
        check_sets_write_roles(user, ["mast-write", "jet-write"], ["mast-write"])


def test_check_sets_write_roles_lets_a_writer_send_the_stored_value_back():
    user = AuthenticatedUser(id="u", roles=("mast-write",))
    check_sets_write_roles(user, ["mast-write"], ["mast-write"])
