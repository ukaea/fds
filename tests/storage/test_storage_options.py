import json

import pytest
from pydantic import TypeAdapter

from app.models.storage_options import (
    FsspecS3StorageOptions,
    IcechunkS3StorageOptions,
    StorageLocation,
    StorageOptions,
    StorageOptionsType,
    build_storage_options,
    derive_storage_options_type,
    parse_storage_url,
    storage_backend,
)


def test_build_fsspec_anonymous():
    opts = build_storage_options(
        StorageOptionsType.FSSPEC_S3,
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        anonymous=True,
    )
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.anon is True
    assert opts.client_kwargs == {
        "endpoint_url": "http://localhost:9000",
        "region_name": "us-east-1",
    }
    assert opts.key is None and opts.secret is None and opts.token is None


def test_build_fsspec_credentialed():
    opts = build_storage_options(
        StorageOptionsType.FSSPEC_S3,
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        access_key_id="AK",
        secret_access_key="SK",
        session_token="ST",
    )
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.key == "AK"
    assert opts.secret == "SK"
    assert opts.token == "ST"
    assert opts.anon is None


def test_build_fsspec_no_region():
    opts = build_storage_options(
        StorageOptionsType.FSSPEC_S3,
        endpoint_url="http://localhost:9000",
        anonymous=True,
    )
    assert isinstance(opts, FsspecS3StorageOptions)
    assert opts.client_kwargs == {"endpoint_url": "http://localhost:9000"}


def test_build_icechunk_anonymous_minio():
    opts = build_storage_options(
        StorageOptionsType.ICECHUNK_S3,
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        anonymous=True,
    )
    assert isinstance(opts, IcechunkS3StorageOptions)
    assert opts.region == "us-east-1"
    assert opts.endpoint_url == "http://localhost:9000"
    assert opts.anonymous is True
    assert opts.allow_http is True
    assert opts.force_path_style is True
    assert opts.access_key_id is None


def test_build_icechunk_anonymous_aws():
    opts = build_storage_options(
        StorageOptionsType.ICECHUNK_S3,
        endpoint_url="https://s3.us-east-1.amazonaws.com",
        region="us-east-1",
        anonymous=True,
    )
    assert isinstance(opts, IcechunkS3StorageOptions)
    assert opts.allow_http is None
    assert opts.force_path_style is None


def test_lookalike_aws_host_is_not_aws():
    """Only amazonaws.com and its subdomains count as AWS, not a host ending in it."""
    opts = build_storage_options(
        StorageOptionsType.ICECHUNK_S3,
        endpoint_url="https://s3.notamazonaws.com",
        anonymous=True,
    )
    assert isinstance(opts, IcechunkS3StorageOptions)
    assert opts.force_path_style is True


def test_build_icechunk_credentialed():
    opts = build_storage_options(
        StorageOptionsType.ICECHUNK_S3,
        endpoint_url="http://localhost:9000",
        region="eu-west-2",
        access_key_id="AK",
        secret_access_key="SK",
        session_token="ST",
    )
    assert isinstance(opts, IcechunkS3StorageOptions)
    assert opts.access_key_id == "AK"
    assert opts.secret_access_key == "SK"
    assert opts.session_token == "ST"
    assert opts.region == "eu-west-2"
    assert opts.anonymous is None


@pytest.mark.parametrize(
    ("url", "backend"),
    [
        ("s3://bucket/key", "s3"),
        ("gs://bucket/key", "gcs"),
        ("gcs://bucket/key", "gcs"),
        ("az://container/blob", "azure"),
        ("abfs://container/blob", "azure"),
        ("abfss://container/blob", "azure"),
        ("https://example.org/file.nc", None),
        (None, None),
    ],
)
def test_storage_backend_from_scheme(url, backend):
    assert storage_backend(url) == backend


@pytest.mark.parametrize(
    ("url", "location"),
    [
        ("s3://bucket/shots/a.nc", StorageLocation("s3", "bucket", "shots/a.nc")),
        ("gs://bucket/key", StorageLocation("gcs", "bucket", "key")),
        ("gcs://bucket/key", StorageLocation("gcs", "bucket", "key")),
        ("az://container/blob", StorageLocation("azure", "container", "blob")),
        ("abfs://container/blob", StorageLocation("azure", "container", "blob")),
        ("abfss://container/blob", StorageLocation("azure", "container", "blob")),
        # The account in the host, as adlfs reads it.
        (
            "abfs://container@acct.dfs.core.windows.net/blob",
            StorageLocation("azure", "container", "blob", "acct"),
        ),
        (
            "az://container@acct.blob.core.windows.net/blob",
            StorageLocation("azure", "container", "blob", "acct"),
        ),
        ("abfs://@acct.dfs.core.windows.net/blob", None),
        ("s3://bucket", StorageLocation("s3", "bucket", "")),
        ("s3://bucket/", StorageLocation("s3", "bucket", "")),
        # Legal in object keys, so not a fragment or a query.
        ("s3://bucket/shots/a#1.nc", StorageLocation("s3", "bucket", "shots/a#1.nc")),
        ("s3://bucket/shots/a?1.nc", StorageLocation("s3", "bucket", "shots/a?1.nc")),
        # Only the leading scheme is stripped.
        ("s3://bucket/copy/s3://x", StorageLocation("s3", "bucket", "copy/s3://x")),
        ("s3://", None),
        ("s3:bucket/key", None),
        ("https://example.org/file.nc", None),
        (None, None),
    ],
)
def test_parse_storage_url(url, location):
    assert parse_storage_url(url) == location


def test_derive_storage_options_type():
    """For S3 URLs: icechunk media-type → icechunk_s3, else fsspec_s3.
    For non-S3 URLs (HTTPS download, MDSplus refs, etc.) and missing URLs: None.
    """
    s3_url = "s3://bucket/key"
    assert (
        derive_storage_options_type("application/vnd.icechunk+zarr", s3_url)
        is StorageOptionsType.ICECHUNK_S3
    )
    assert (
        derive_storage_options_type("application/x-zarr", s3_url)
        is StorageOptionsType.FSSPEC_S3
    )
    assert (
        derive_storage_options_type("application/netcdf", s3_url)
        is StorageOptionsType.FSSPEC_S3
    )
    assert derive_storage_options_type(None, s3_url) is StorageOptionsType.FSSPEC_S3
    # Non-S3 URLs opt out — distribution is accessed via URL directly.
    assert derive_storage_options_type("text/csv", "https://example/file.csv") is None
    assert derive_storage_options_type(None, "mdsplus://server/tree") is None
    assert derive_storage_options_type(None, None) is None


def test_schema_declares_no_discriminator():
    """The published schema must not name a discriminator the payload lacks.

    Every key is splatted into an opener, so there is no tag to send, and a
    client generated from the schema fails looking for one.
    """
    schema = TypeAdapter(StorageOptions).json_schema(mode="serialization")
    assert "discriminator" not in json.dumps(schema)


def test_serialised_drops_unset_keys():
    """Unset keys must not reach the wire as nulls.

    ``icechunk.s3_storage`` takes ``bucket`` and ``prefix`` from the caller, so
    a serialised ``bucket: null`` makes ``s3_storage(bucket=..., **opts)`` raise
    rather than open the store. The same holds for every other unset key.
    """
    icechunk_dump = build_storage_options(
        StorageOptionsType.ICECHUNK_S3,
        endpoint_url="http://localhost:9000",
        access_key_id="AK",
        secret_access_key="SK",
        session_token="ST",
    ).model_dump(exclude_none=True)
    assert "bucket" not in icechunk_dump
    assert "prefix" not in icechunk_dump
    assert "anonymous" not in icechunk_dump
    assert icechunk_dump["force_path_style"] is True

    fsspec_dump = build_storage_options(
        StorageOptionsType.FSSPEC_S3,
        endpoint_url="http://localhost:9000",
        access_key_id="AK",
        secret_access_key="SK",
        session_token="ST",
    ).model_dump(exclude_none=True)
    assert "anon" not in fsspec_dump
    assert fsspec_dump["key"] == "AK"
