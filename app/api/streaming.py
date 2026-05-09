"""NDJSON streaming helpers for the bulk-export endpoints (ADR-0020)."""

from collections.abc import Iterable, Iterator

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

NDJSON_MEDIA_TYPE = "application/x-ndjson"


def serialize_ndjson(rows: Iterable[BaseModel]) -> Iterator[bytes]:
    """Yield NDJSON-encoded bytes for each row, one row per line.

    Each row is serialised with Pydantic's ``model_dump_json`` (which respects
    the model's field config, including ``exclude_none`` if set on the model).
    Lines are terminated with a single ``\\n``, including the final line — this
    matches the de-facto NDJSON convention and keeps line-oriented parsers happy.
    """
    for row in rows:
        yield row.model_dump_json(exclude_none=True).encode("utf-8")
        yield b"\n"


def ndjson_response(rows: Iterable[BaseModel]) -> StreamingResponse:
    """Wrap an iterable of Pydantic models in an NDJSON ``StreamingResponse``."""
    return StreamingResponse(serialize_ndjson(rows), media_type=NDJSON_MEDIA_TYPE)
