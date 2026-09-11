from collections.abc import Iterable
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import drain_restricted_access, request_context

logger = structlog.get_logger("fds.audit")

SKIP_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


class AuditMiddleware:
    """Seeds the request context and emits one audit line per request."""

    def __init__(self, app: ASGIApp, /) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path", "") in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        response: dict[str, Any] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response["status"] = message["status"]
                response["bytes"] = _content_length(message.get("headers", []))
            await send(message)

        with request_context() as context:
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                route = scope.get("route")
                logger.info(
                    "request",
                    method=scope.get("method"),
                    route=getattr(route, "path", None) or scope.get("path"),
                    path=scope.get("path"),
                    # No status means the app raised before responding.
                    status=response.get("status", 500),
                    response_bytes=response.get("bytes"),
                    returned=context.returned,
                    truncated=context.truncated,
                    **drain_restricted_access(),
                )


def _content_length(headers: Iterable[tuple[bytes, bytes]]) -> int | None:
    for name, value in headers:
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
