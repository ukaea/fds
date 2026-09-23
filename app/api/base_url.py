from functools import cache

import structlog
from fastapi import Request

from app.core.config import config
from app.services.identifiers import resolve_base

logger = structlog.get_logger(__name__)


@cache  # once per distinct answer, not once per request
def _warn_about_guessing(base: str, forwarded_proto: str) -> None:
    logger.warning(
        "identifiers.base_guessed_behind_proxy",
        derived_base=base,
        forwarded_proto=forwarded_proto,
        detail=(
            "This request came through a proxy whose forwarded headers were not "
            "trusted, so identifiers are being published under the address above, "
            "which is not the one callers used. Set FDS_BASE_URL."
        ),
    )


def get_base_url(request: Request) -> str:
    base = resolve_base(config.base_url, str(request.base_url))

    if not config.base_url.strip():
        forwarded_proto = request.headers.get("x-forwarded-proto")
        if forwarded_proto is not None and forwarded_proto != request.url.scheme:
            _warn_about_guessing(base, forwarded_proto)

    return base
