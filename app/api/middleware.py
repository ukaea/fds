from collections.abc import Iterable
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import drain_restricted_access, request_context

logger = structlog.get_logger("fds.audit")

SKIP_PATHS = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})


def route_template(scope: Scope) -> str | None:
    """The matched route's path with its parameters as ``{name}`` placeholders.

    Since FastAPI 0.122 a router included with a prefix keeps its own paths, so
    ``scope["route"].path`` is only the tail (``/{shot}/datasets/{name}``) and
    nothing in the scope carries the prefixes above it. The tail is exact, so it
    is used as-is; the prefix is the leading part of the concrete path with the
    remaining parameters substituted back in, segment by segment.
    """
    route = scope.get("route")
    tail = getattr(route, "path", None)
    path = scope.get("path")
    if not tail or not path:
        return path
    params: dict[str, Any] = scope.get("path_params") or {}

    tail_segments = tail.strip("/").split("/")
    path_segments = path.strip("/").split("/")
    if len(path_segments) < len(tail_segments):
        return path
    head = path_segments[: len(path_segments) - len(tail_segments)]

    # Parameters the tail already names are accounted for; the rest belong to
    # the prefix. In a REST path a value follows the literal that names its
    # collection, so walking right to left and taking the last unclaimed match
    # keeps a value that also appears as a literal (a device called "devices")
    # from being rewritten in the wrong place.
    in_tail = {seg[1:-1] for seg in tail_segments if seg[:1] == "{" and seg[-1:] == "}"}
    for name, value in reversed(list(params.items())):
        if name in in_tail:
            continue
        for i in range(len(head) - 1, -1, -1):
            if head[i] == str(value):
                head[i] = f"{{{name}}}"
                break

    return "/" + "/".join(head + tail_segments)


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
                logger.info(
                    "request",
                    method=scope.get("method"),
                    route=route_template(scope),
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
