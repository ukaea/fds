from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel


class StorageOptionsType(str, Enum):
    """Discriminator for the consumer library that ``storage_options`` targets."""

    FSSPEC_S3 = "fsspec_s3"
    ICECHUNK_S3 = "icechunk_s3"


StorageBackend = Literal["s3", "gcs", "azure"]

_BACKEND_BY_SCHEME: dict[str, StorageBackend] = {
    "s3": "s3",
    "gs": "gcs",
    "gcs": "gcs",
    "az": "azure",
    "abfs": "azure",
}

_AWS_HOSTS = ("amazonaws.com",)


def storage_backend(url: str | None) -> StorageBackend | None:
    """The object store a URL points at, read from its scheme.

    ``None`` for anything that is not an object store, such as an HTTPS
    download or an MDSplus reference.
    """
    if not url:
        return None
    return _BACKEND_BY_SCHEME.get(urlparse(url).scheme)


class FsspecS3StorageOptions(BaseModel):
    """fsspec/s3fs storage options for S3 / S3-compatible backends.

    Splat-compatible with ``s3fs.S3FileSystem(**opts)`` and consumed directly
    by xarray, dask, zarr, pyarrow via their ``storage_options=`` parameter.
    """

    key: str | None = None
    secret: str | None = None
    token: str | None = None
    anon: bool | None = None
    client_kwargs: dict[str, str] | None = None


class IcechunkS3StorageOptions(BaseModel):
    """icechunk ``s3_storage()`` shape for S3 / S3-compatible backends.

    Splat-compatible with ``icechunk.s3_storage(**opts)``.
    """

    bucket: str | None = None
    prefix: str | None = None
    region: str | None = None
    endpoint_url: str | None = None
    anonymous: bool | None = None
    allow_http: bool | None = None
    force_path_style: bool | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None


class FsspecAzureStorageOptions(BaseModel):
    """adlfs storage options for Azure Blob Storage.

    Splat-compatible with ``adlfs.AzureBlobFileSystem(**opts)``. An ``az://``
    URL names the container but not the storage account, so ``account_name``
    is needed even for anonymous access.
    """

    account_name: str | None = None
    sas_token: str | None = None
    anon: bool | None = None


class FsspecGCSStorageOptions(BaseModel):
    """gcsfs storage options for Google Cloud Storage.

    Splat-compatible with ``gcsfs.GCSFileSystem(**opts)``. ``token`` is a
    short-lived access token, or ``"anon"`` for a public bucket.
    """

    token: str


# A plain union: every key is splatted into an opener, so the payload carries
# no tag a discriminator could read, and the OpenAPI schema must not claim one.
StorageOptions = (
    FsspecS3StorageOptions
    | IcechunkS3StorageOptions
    | FsspecAzureStorageOptions
    | FsspecGCSStorageOptions
)


def derive_storage_options_type(
    media_type: str | None, url: str | None
) -> StorageOptionsType | None:
    """Pick the natural ``storage_options`` shape for a Distribution.

    Only S3 offers a choice of library, so every other URL gets ``None``.
    Azure and GCS still get ``storage_options``, in the one shape their
    scheme implies; anything else is opened by its URL alone.

    For S3-scheme URLs:
        ``application/vnd.icechunk+zarr`` → :class:`StorageOptionsType.ICECHUNK_S3`
        anything else → :class:`StorageOptionsType.FSSPEC_S3`
    """
    if storage_backend(url) != "s3":
        return None
    if media_type and "icechunk" in media_type.lower():
        return StorageOptionsType.ICECHUNK_S3
    return StorageOptionsType.FSSPEC_S3


def _is_non_aws(endpoint_url: str | None) -> bool:
    if not endpoint_url:
        return False
    host = urlparse(endpoint_url).hostname or ""
    return not any(host == d or host.endswith(f".{d}") for d in _AWS_HOSTS)


def build_storage_options(
    target_type: StorageOptionsType,
    *,
    endpoint_url: str | None = None,
    region: str | None = None,
    anonymous: bool = False,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    session_token: str | None = None,
) -> StorageOptions:
    """Construct an opener-ready StorageOptions value.

    Returns connection-level options only — ``bucket``/``prefix`` for the
    icechunk shape are left unset because the caller chooses which URL to open
    (a Distribution's ``url`` for a standalone NetCDF / Zarr, or a Collection's
    ``root_url`` for an IceChunk store containing the Distribution as a group).

    Defaults that consumers shouldn't need to know (path-style addressing for
    non-AWS S3, http transport for plain-http endpoints) are filled in here.
    """
    if target_type is StorageOptionsType.FSSPEC_S3:
        client_kwargs: dict[str, str] = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if region:
            client_kwargs["region_name"] = region
        return FsspecS3StorageOptions(
            key=access_key_id,
            secret=secret_access_key,
            token=session_token,
            anon=True if anonymous else None,
            client_kwargs=client_kwargs or None,
        )

    return IcechunkS3StorageOptions(
        region=region,
        endpoint_url=endpoint_url,
        anonymous=True if anonymous else None,
        allow_http=True
        if endpoint_url and endpoint_url.startswith("http://")
        else None,
        force_path_style=True if _is_non_aws(endpoint_url) else None,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        session_token=session_token,
    )
