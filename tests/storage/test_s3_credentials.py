"""Credential vending against a faked STS.

`S3CredentialProvider.generate_credentials` had no test: the policy it builds
was covered, but the AssumeRole call, the mapping of the response onto
`S3Credentials`, and the bucket keying were only ever exercised by hand against
a real store. These run the real boto3 client against moto, so the call and its
response shape are checked without anything to run.

What no local test can show is that a particular store's STS behaves like AWS's.
That is a check against the store, at deployment.
"""

import os
from datetime import datetime
from typing import Any

import pytest

from app.core.config import S3StorageProvider
from app.services.exceptions import ConfigurationError

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

from app.core.storage.s3_provider import S3CredentialProvider

ROLE_ARN = "arn:aws:iam::123456789012:role/fds-role"


@pytest.fixture(autouse=True)
def aws_credentials():
    """moto refuses to run without credentials in the environment."""
    previous = {
        key: os.environ.get(key)
        for key in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SECURITY_TOKEN",
            "AWS_SESSION_TOKEN",
            "AWS_DEFAULT_REGION",
        )
    }
    os.environ.update(
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing",
            "AWS_DEFAULT_REGION": "us-east-1",
        }
    )
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# moto intercepts AWS endpoints, so the STS calls are aimed at one while the
# client-facing endpoint stays a custom store. That is also the arrangement worth
# testing: FDS calls one address and tells clients another.
STS_ENDPOINT = "https://sts.us-east-1.amazonaws.com"
CLIENT_ENDPOINT = "https://s3.example.org"


def provider(**overrides: Any) -> S3CredentialProvider:
    settings: dict[str, Any] = {
        "endpoint_url": CLIENT_ENDPOINT,
        "region": "us-east-1",
        "sts_endpoint_url": STS_ENDPOINT,
        "sts_role_arn": ROLE_ARN,
    } | overrides
    return S3CredentialProvider(S3StorageProvider(**settings))


def test_credentials_are_vended_per_bucket():
    with moto.mock_aws():
        vended = provider().generate_credentials(
            ["s3://alpha/shots/1", "s3://beta/shots/2"], "session-name"
        )

    assert set(vended) == {"alpha", "beta"}
    for credentials in vended.values():
        assert credentials.access_key_id
        assert credentials.secret_access_key
        assert credentials.session_token
        assert isinstance(credentials.expiration, datetime)
        # The client-facing endpoint, not the one FDS called to mint these.
        assert credentials.endpoint_url == CLIENT_ENDPOINT
        assert credentials.region == "us-east-1"


def test_one_token_covers_every_bucket_it_was_minted_for():
    """STS credentials are not bucket-scoped; the map is a convenience."""
    with moto.mock_aws():
        vended = provider().generate_credentials(
            ["s3://alpha/a", "s3://beta/b"], "session-name"
        )

    assert vended["alpha"].session_token == vended["beta"].session_token


def test_configured_keys_are_used_when_given():
    """Explicit keys take precedence over the ambient credential chain."""
    with moto.mock_aws():
        vended = provider(
            sts_access_key_id="AKIAFDS", sts_secret_access_key="secret"
        ).generate_credentials(["s3://alpha/a"], "session-name")

    assert vended["alpha"].session_token


def test_a_refused_assume_role_is_reported_as_configuration():
    """An unassumable role is a deployment fault, not a caller's."""
    with moto.mock_aws():
        unassumable = provider(sts_role_arn="not-an-arn")
        with pytest.raises(ConfigurationError, match="not-an-arn"):
            unassumable.generate_credentials(["s3://alpha/a"], "session-name")


def test_wildcard_prefix_is_refused():
    """Vending for every bucket would defeat the point of scoping."""
    with moto.mock_aws(), pytest.raises(ConfigurationError, match="Wildcard"):
        provider().generate_credentials(["*"], "session-name")
