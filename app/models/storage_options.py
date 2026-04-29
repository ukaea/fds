from enum import Enum
from typing import Annotated, Literal, Union
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class StorageOptionsType(str, Enum):
    """Discriminator for the consumer library that ``storage_options`` targets."""

    FSSPEC_S3 = "fsspec_s3"
    ICECHUNK_S3 = "icechunk_s3"


_AWS_HOSTS = ("amazonaws.com",)


class FsspecS3StorageOptions(BaseModel):
    """fsspec/s3fs storage options for S3 / S3-compatible backends.

    Splat-compatible with ``s3fs.S3FileSystem(**opts)`` and consumed directly
    by xarray, dask, zarr, pyarrow via their ``storage_options=`` parameter.

    The ``type`` discriminator is excluded from serialised output so the dict
    can be passed straight to ``s3fs.S3FileSystem`` / ``xr.open_dataset``
    without further filtering.
    """

    type: Literal[StorageOptionsType.FSSPEC_S3] = Field(
        default=StorageOptionsType.FSSPEC_S3, exclude=True
    )
    key: str | None = None
    secret: str | None = None
    token: str | None = None
    anon: bool | None = None
    client_kwargs: dict[str, str] | None = None


class IcechunkS3StorageOptions(BaseModel):
    """icechunk ``s3_storage()`` shape for S3 / S3-compatible backends.

    Splat-compatible with ``icechunk.s3_storage(**opts)``. The ``type``
    discriminator is excluded from serialised output.
    """

    type: Literal[StorageOptionsType.ICECHUNK_S3] = Field(
        default=StorageOptionsType.ICECHUNK_S3, exclude=True
    )
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


StorageOptions = Annotated[
    Union[FsspecS3StorageOptions, IcechunkS3StorageOptions],
    Field(discriminator="type"),
]


def derive_storage_options_type(
    media_type: str | None, url: str | None
) -> StorageOptionsType | None:
    """Pick the natural ``storage_options`` shape for a Distribution.

    Returns ``None`` for distributions where automated storage_options doesn't
    apply (HDF5 / CSV / blob downloads over HTTPS, MDSplus references, etc.) —
    these are accessed via their URL directly, no SDK kwargs needed.

    For S3-scheme URLs:
        ``application/vnd.icechunk+zarr`` → :class:`StorageOptionsType.ICECHUNK_S3`
        anything else → :class:`StorageOptionsType.FSSPEC_S3`
    """
    if not url:
        return None
    if urlparse(url).scheme != "s3":
        return None
    if media_type and "icechunk" in media_type.lower():
        return StorageOptionsType.ICECHUNK_S3
    return StorageOptionsType.FSSPEC_S3


def _is_non_aws(endpoint_url: str | None) -> bool:
    if not endpoint_url:
        return False
    host = urlparse(endpoint_url).hostname or ""
    return not any(host.endswith(suffix) for suffix in _AWS_HOSTS)


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
