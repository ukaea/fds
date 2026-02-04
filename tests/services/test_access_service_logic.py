from unittest.mock import patch

import pytest
from sqlmodel import Session

from app.models.dataset import Dataset
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.exceptions import ForbiddenError
from app.services.file_access_service import FileAccessService


@pytest.fixture
def access_service(session: Session):
    return FileAccessService(session)


@pytest.fixture
def mock_check_shot_operator():
    with patch("app.services.file_access_service.check_shot_operator") as mock:
        yield mock


def test_access_public_anonymous(access_service):
    """Public datasets should be accessible to anonymous users."""
    dataset = Dataset(
        name="pub", level=1, data_url="s3://pub", access_level=AccessLevel.PUBLIC
    )
    assert access_service._check_download_permission(ANONYMOUS_USER, dataset) is True


def test_access_public_authenticated(access_service):
    """Public datasets should be accessible to authenticated users."""
    user = AuthenticatedUser(id="u1", scopes=[])
    dataset = Dataset(
        name="pub", level=1, data_url="s3://pub", access_level=AccessLevel.PUBLIC
    )
    assert access_service._check_download_permission(user, dataset) is True


def test_access_required_scope_allowed(access_service):
    """Dataset with required_scope should be accessible to user having that scope."""
    user = AuthenticatedUser(id="u1", scopes=["special:access"])
    dataset = Dataset(
        name="scoped",
        level=1,
        data_url="s3://scoped",
        access_level=AccessLevel.RESTRICTED,
        required_scope="special:access",
    )
    assert access_service._check_download_permission(user, dataset) is True


def test_access_required_scope_denied(access_service):
    """Dataset with required_scope should be DENIED to user lacking that scope."""
    user = AuthenticatedUser(id="u1", scopes=["wrong:scope"])
    dataset = Dataset(
        name="scoped",
        level=1,
        data_url="s3://scoped",
        access_level=AccessLevel.RESTRICTED,
        required_scope="special:access",
    )
    assert access_service._check_download_permission(user, dataset) is False


def test_access_required_scope_overrides_fallback(
    access_service, mock_check_shot_operator
):
    """If required_scope is set, fallback context check should NOT act (Specific Overrides General)."""
    # User HAS shot operator (context), but LACKS required_scope.
    # Should FAIL.
    user = AuthenticatedUser(id="u1", scopes=["shot-operator:mast"])
    dataset = Dataset(
        name="override",
        level=1,
        data_url="s3://override",
        access_level=AccessLevel.RESTRICTED,
        required_scope="special:top-secret",
        device_name="mast",
    )

    allowed = access_service._check_download_permission(user, dataset)
    assert allowed is False
    # Ensure fallback was NOT called (optimization/strictness check)
    mock_check_shot_operator.assert_not_called()


def test_access_fallback_shot_context_allowed(access_service, mock_check_shot_operator):
    """If no required_scope, should fallback to Shot Context check."""
    user = AuthenticatedUser(id="u1", scopes=[])
    dataset = Dataset(
        name="fallback",
        level=1,
        data_url="s3://fallback",
        access_level=AccessLevel.RESTRICTED,  # or Embargoed
        device_name="mast",
        shot_id="123",
    )
    # Mock fallback passing
    mock_check_shot_operator.return_value = None  # logic returns None on success

    assert access_service._check_download_permission(user, dataset) is True
    mock_check_shot_operator.assert_called_with(user, "mast")


def test_access_fallback_shot_context_denied(access_service, mock_check_shot_operator):
    """If no required_scope, should fallback to Shot Context check (failing)."""
    user = AuthenticatedUser(id="u1", scopes=[])
    dataset = Dataset(
        name="fallback",
        level=1,
        data_url="s3://fallback",
        access_level=AccessLevel.RESTRICTED,
        device_name="mast",
        shot_id="123",
    )
    # Mock fallback failing
    mock_check_shot_operator.side_effect = ForbiddenError("Access denied")

    assert access_service._check_download_permission(user, dataset) is False


@patch("app.services.file_access_service.urlparse")
def test_fail_fast_malformed_url(mock_urlparse, access_service):
    """FileAccessService should propagate exceptions for malformed URLs (Fail Fast), not swallow them."""
    # Simulate urlparse raising ValueError (which happens for some bad IPv6 literals)
    mock_urlparse.side_effect = ValueError("Invalid URL")

    with pytest.raises(ValueError, match="Invalid URL"):
        access_service._group_urls_by_protocol(["http://bad-url"])
