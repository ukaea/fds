from app.models.storage_options import (
    FsspecS3StorageOptions,
    IcechunkS3StorageOptions,
    StorageOptionsType,
    build_storage_options,
    derive_storage_options_type,
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


def test_serialised_excludes_type_discriminator():
    """The ``type`` discriminator is metadata for the API contract — it must
    not leak into serialised output, otherwise consumers can't splat directly
    into ``s3fs.S3FileSystem(**opts)`` or ``icechunk.s3_storage(**opts)``.
    """
    fsspec_dump = build_storage_options(
        StorageOptionsType.FSSPEC_S3, endpoint_url="http://x", anonymous=True
    ).model_dump()
    assert "type" not in fsspec_dump

    icechunk_dump = build_storage_options(
        StorageOptionsType.ICECHUNK_S3, endpoint_url="http://x", anonymous=True
    ).model_dump()
    assert "type" not in icechunk_dump
