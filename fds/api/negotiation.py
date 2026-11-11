from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse

from fds.api.base_url import get_base_url

LD_JSON = "application/ld+json"
JSON = "application/json"

# A route that answers in JSON or JSON-LD by the Accept header sends this with
# both answers, so that a cache never hands one to a caller that asked for the
# other.
VARY_ACCEPT = {"Vary": "Accept"}

# For the ``responses`` of a route that also answers in JSON-LD, so that its
# OpenAPI description offers both media types.
JSONLD_ALTERNATIVE: dict[int | str, dict[str, Any]] = {
    200: {"content": {LD_JSON: {"schema": {"type": "object"}}}}
}


class JSONLDResponse(JSONResponse):
    """A JSON-LD document, served as ``application/ld+json``."""

    media_type = LD_JSON


class Answer:
    """Answers a request in JSON or JSON-LD, whichever its Accept header prefers.

    Routes take it as a dependency, ``AnswerDep``, and call it with both answers
    as functions, so that only the one sent is built. The JSON-LD one is given
    the base URL its identifiers are written under.

    FastAPI passes it the response it will send with a plain JSON answer, which
    is marked as varying with the Accept header. A JSON-LD answer is a
    ``JSONLDResponse`` of its own, so it carries ``VARY_ACCEPT`` itself.
    """

    def __init__(
        self,
        request: Request,
        response: Response,
        base: Annotated[str, Depends(get_base_url)],
    ) -> None:
        response.headers.update(VARY_ACCEPT)
        self.wants_jsonld = self.prefers_jsonld(request.headers.get("accept"))
        self.base = base

    @staticmethod
    def prefers_jsonld(accept: str | None) -> bool:
        """Whether an Accept header asks for JSON-LD rather than plain JSON.

        It does when it gives ``application/ld+json`` a higher q-value than
        ``application/json``, or the same one while naming ``application/ld+json``
        itself. A q-value of 0 means "not this", and a range whose q-value is not
        a number is left out. With no Accept header, or one that reaches both
        only through ``*/*`` or ``application/*``, the answer is plain JSON.
        """
        # Each media type takes the q-value of the most specific range that names
        # it: the type itself (2), then its type with any subtype (1), then */* (0).
        best = {LD_JSON: (0.0, -1), JSON: (0.0, -1)}
        for part in (accept or "").split(","):
            media_range, *parameters = (p.strip().lower() for p in part.split(";"))
            quality = 1.0
            for name, _, value in (
                parameter.partition("=") for parameter in parameters
            ):
                if name.strip() == "q":
                    try:
                        quality = float(value)
                    except ValueError:
                        quality = -1.0
            if quality < 0:
                continue
            for media_type in best:
                kind = media_type.split("/")[0]
                closeness = {media_type: 2, f"{kind}/*": 1, "*/*": 0}.get(
                    media_range, -1
                )
                if closeness > best[media_type][1]:
                    best[media_type] = (quality, closeness)
        (jsonld, jsonld_closeness), (plain, _) = best[LD_JSON], best[JSON]
        if jsonld <= 0:
            return False
        return jsonld > plain or (jsonld == plain and jsonld_closeness == 2)

    def __call__[T](
        self, *, json: Callable[[], T], jsonld: Callable[[str], dict[str, Any]]
    ) -> T | JSONLDResponse:
        if self.wants_jsonld:
            return JSONLDResponse(content=jsonld(self.base), headers=VARY_ACCEPT)
        return json()
