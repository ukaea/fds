import pytest
from pydantic import ValidationError

from app.core.config import Config

AWS = {"type": "s3", "endpoint_url": None, "region": "r", "sts_role_arn": "arn:a"}


def test_storage_providers_duplicate_rejected():
    """The second would never be chosen, so its datasets would get the first's credentials."""
    with pytest.raises(ValidationError, match="duplicate provider"):
        Config.model_validate(
            {"FDS_STORAGE_PROVIDERS": [AWS, AWS | {"sts_role_arn": "arn:b"}]}
        )


def test_storage_providers_of_different_types_may_share_an_endpoint():
    config = Config.model_validate(
        {"FDS_STORAGE_PROVIDERS": [AWS, {"type": "gcs", "endpoint_url": None}]}
    )

    assert [p.type for p in config.STORAGE_PROVIDERS] == ["s3", "gcs"]
