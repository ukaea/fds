import json

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from fastmcp.resources import ResourceResult
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import InputRequiredToolResult, ToolResult
from mcp_types import CallToolRequestParams, ReadResourceRequestParams, TextContent
from starlette.types import ASGIApp, Receive, Scope, Send

from fds.api.protected_resource import (
    METADATA_PATH,
    address_called,
    bearer_challenge,
    sent_a_token,
)
from fds.auth.jwks import get_jwks_client
from fds.auth.security import get_token_claims


class RefuseInvalidTokens:
    """The MCP server, behind the check FDS makes of every token.

    A request with no token goes through, and its tools read public records. A
    request with a token FDS would refuse is answered 401 before the MCP server
    sees it, because a 401 is what tells a client to get a fresh token: a tool
    error would only tell the model."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        if sent_a_token(request):
            token = request.headers["authorization"][7:].strip()
            try:
                await get_token_claims(
                    get_jwks_client(),
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                )
            except HTTPException as refused:
                headers = None
                if refused.status_code == 401:
                    challenge = bearer_challenge(request, "invalid_token", "/mcp")
                    headers = {"WWW-Authenticate": challenge}
                response = JSONResponse(
                    {"detail": refused.detail},
                    status_code=refused.status_code,
                    headers=headers,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def not_signed_in_notice() -> str | None:
    """What to tell the model when no token came with this MCP request, or None
    when one did."""
    request = get_http_request()
    if sent_a_token(request):
        return None
    metadata = f"{address_called(request)}{METADATA_PATH}/mcp"
    return (
        "No token came with this request, so these results include public records "
        "only. To see restricted records, log in to this server through your MCP "
        f"client. The client finds where to log in from {metadata}. If it asks for "
        "a client ID, ask whoever runs this FDS."
    )


class NoteWhenNotSignedIn(Middleware):
    """Adds `not_signed_in` to every tool result and record read without a
    token, so the model can say the answer covers public records only instead
    of answering as if the catalogue held nothing more."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        notice = not_signed_in_notice()
        # A tool asking the user a question has no results to qualify yet.
        if notice is None or isinstance(result, InputRequiredToolResult):
            return result
        if result.structured_content is not None:
            return ToolResult(
                structured_content={
                    **result.structured_content,
                    "not_signed_in": notice,
                },
                meta=result.meta,
                is_error=result.is_error,
            )
        return ToolResult(
            content=[*result.content, TextContent(type="text", text=notice)],
            meta=result.meta,
            is_error=result.is_error,
        )

    async def on_read_resource(
        self,
        context: MiddlewareContext[ReadResourceRequestParams],
        call_next: CallNext[ReadResourceRequestParams, ResourceResult],
    ) -> ResourceResult:
        result = await call_next(context)
        notice = not_signed_in_notice()
        if notice is None:
            return result
        for content in result.contents:
            if content.mime_type == "application/json" and isinstance(
                content.content, str
            ):
                record = json.loads(content.content)
                if isinstance(record, dict):
                    record["not_signed_in"] = notice
                    content.content = json.dumps(record)
        return result
