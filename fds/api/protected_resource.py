from typing import Any

from fastapi import APIRouter, Request

from fds.core.config import config

METADATA_PATH = "/.well-known/oauth-protected-resource"

# Left out of the OpenAPI description: a program finds these documents from the
# WWW-Authenticate header of a 401, or from the address it called.
router = APIRouter(include_in_schema=False)


def address_called(request: Request) -> str:
    """The address the caller reached FDS on, such as https://api.example.org."""
    return str(request.base_url).rstrip("/")


def sent_a_token(request: Request) -> bool:
    return request.headers.get("authorization", "")[:7].lower() == "bearer "


def bearer_challenge(
    request: Request, error: str | None = None, resource_path: str = ""
) -> str:
    """The WWW-Authenticate value that names the document saying where to get a
    token. `resource_path` is empty for the API and `/mcp` for the MCP server."""
    metadata = f"{address_called(request)}{METADATA_PATH}{resource_path}"
    parts = [f'error="{error}"'] if error else []
    parts.append(f'resource_metadata="{metadata}"')
    return "Bearer " + ", ".join(parts)


def protected_resource_metadata(resource: str) -> dict[str, Any]:
    """What a program needs to get a token for `resource`: the login services
    whose tokens FDS accepts, and the scope to ask them for.

    An issuer whose keys FDS reads from a file is left out: its tokens are signed
    offline, so nobody can log in there."""
    document: dict[str, Any] = {"resource": resource}
    issuers = [idp.issuer for idp in config.TRUSTED_IDPS if idp.jwks_file is None]
    if issuers:
        document["authorization_servers"] = issuers
    scopes = config.OIDC_SCOPE.split()
    if scopes:
        document["scopes_supported"] = scopes
    document["bearer_methods_supported"] = ["header"]
    return document


@router.get(METADATA_PATH)
def api_metadata(request: Request) -> dict[str, Any]:
    return protected_resource_metadata(address_called(request))


@router.get(f"{METADATA_PATH}/mcp")
def mcp_metadata(request: Request) -> dict[str, Any]:
    return protected_resource_metadata(f"{address_called(request)}/mcp")
