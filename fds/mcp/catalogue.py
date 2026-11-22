from typing import Any

import httpx2 as httpx
from fastmcp.exceptions import ToolError

MAX_PAGE = 50


class Catalogue:
    """Read requests to FDS's API on behalf of the person whose MCP request is
    being answered. The requests go to `api`, the address that person used, and
    carry their `authorization` header, so FDS answers each one as it would answer
    them. Every failure is raised as a ToolError whose message the model can act
    on."""

    def __init__(self, http: httpx.AsyncClient, api: str, authorization: str | None):
        self.http = http
        self.api = api
        self.authorization = authorization
        self.landing_page_base: str | None = None

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": self.authorization} if self.authorization else {}
        response = await self.http.get(
            f"{self.api}{path}", params=without_empty(params or {}), headers=headers
        )
        if response.is_success:
            return response.json()
        raise ToolError(self.explain_failure(response))

    async def page(
        self, path: str, params: dict[str, Any], offset: int, limit: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """One page of a listing, and where the next page starts if there is one.
        FDS listings carry no total, so this asks for one record more than
        `limit` to learn whether another page follows."""
        limit = max(1, min(limit, MAX_PAGE))
        records = await self.get(path, {**params, "offset": offset, "limit": limit + 1})
        paging: dict[str, Any] = {"offset": offset, "returned": len(records[:limit])}
        if len(records) > limit:
            paging["next_offset"] = offset + limit
        return records[:limit], paging

    async def landing_page(self, path: str) -> str | None:
        """The address of a record's page for people, such as
        `http://localhost:3000/datasets/12` for `/datasets/12`. FDS names its own
        address in the catalogue's `@id`, which ends in `/catalog`."""
        if self.landing_page_base is None:
            try:
                catalog = await self.get("/catalog")
            except ToolError:
                return None
            self.landing_page_base = catalog.get("@id", "").removesuffix("/catalog")
        return f"{self.landing_page_base}{path}" if self.landing_page_base else None

    def explain_failure(self, response: httpx.Response) -> str:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        status = response.status_code
        if status in (401, 403):
            if self.authorization:
                return (
                    f"FDS refused access ({status}): {detail}. The token may have "
                    "expired, or this user may not read the record."
                )
            return (
                f"FDS refused access ({status}): {detail}. No token came with the "
                "request, so only public records can be read."
            )
        if status == 404:
            return f"Not found: {detail}"
        return f"FDS answered {status}: {detail}"


def without_empty(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in record.items() if value is not None and value != []
    }
