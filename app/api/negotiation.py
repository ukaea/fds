from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse

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


def _media_ranges(accept: str) -> list[tuple[str, float]]:
    """Each media range in an Accept header, with its q-value.

    A range whose q-value is not a number is left out.
    """
    ranges = []
    for part in accept.split(","):
        media_range, *parameters = (piece.strip() for piece in part.split(";"))
        quality = 1.0
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = -1.0
        if media_range and quality >= 0:
            ranges.append((media_range.lower(), quality))
    return ranges


def _preference(ranges: list[tuple[str, float]], media_type: str) -> tuple[float, int]:
    """The q-value the Accept header gives ``media_type``, and how closely the
    range it comes from names it.

    The most specific range that matches decides: the media type itself (2),
    then its type with any subtype, such as ``application/*`` (1), then ``*/*``
    (0). A media type no range matches has q-value 0 and closeness -1.
    """
    kind = media_type.split("/")[0]
    closeness_of = {media_type: 2, f"{kind}/*": 1, "*/*": 0}
    best = (0.0, -1)
    for media_range, quality in ranges:
        closeness = closeness_of.get(media_range, -1)
        if closeness > best[1]:
            best = (quality, closeness)
    return best


def prefers_jsonld(accept: str | None) -> bool:
    """Whether an Accept header asks for JSON-LD rather than plain JSON.

    It does when it gives ``application/ld+json`` a higher q-value than
    ``application/json``, or the same one while naming ``application/ld+json``
    itself. A q-value of 0 means "not this". With no Accept header, or one that
    reaches both only through ``*/*`` or ``application/*``, the answer is plain
    JSON.
    """
    if not accept:
        return False
    ranges = _media_ranges(accept)
    jsonld, jsonld_closeness = _preference(ranges, LD_JSON)
    plain, _ = _preference(ranges, JSON)
    if jsonld <= 0:
        return False
    return jsonld > plain or (jsonld == plain and jsonld_closeness == 2)


def wants_jsonld(request: Request, response: Response) -> bool:
    """Whether to answer ``request`` in JSON-LD rather than plain JSON.

    Routes take this as a dependency, ``WantsJSONLDDep``, and FastAPI passes it
    the request and the response it will send with a plain JSON answer. That
    response is marked as varying with the Accept header. A JSON-LD answer is
    returned as a ``JSONLDResponse`` of its own, which has to carry
    ``VARY_ACCEPT`` itself.
    """
    response.headers.update(VARY_ACCEPT)
    return prefers_jsonld(request.headers.get("accept"))
