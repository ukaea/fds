import pytest
from pydantic import ValidationError

from fds.core.config import Config

MEMBER = {
    "id": "https://fds.example.org",
    "title": "Another FDS",
    "kind": "fds",
    "url": "https://api.fds.example.org/",
}


def test_federation_members_duplicate_rejected():
    """Two members with one id would be one catalogue asked twice."""
    with pytest.raises(ValidationError, match="duplicate member"):
        Config.model_validate(
            {"FDS_FEDERATION_MEMBERS": [MEMBER, MEMBER | {"title": "Again"}]}
        )


def test_federation_member_url_loses_its_trailing_slash():
    config = Config.model_validate({"FDS_FEDERATION_MEMBERS": [MEMBER]})

    assert config.FEDERATION_MEMBERS[0].url == "https://api.fds.example.org"


def test_federation_has_no_members_by_default():
    assert Config.model_validate({}).FEDERATION_MEMBERS == []
