"""Unit tests for the NDJSON streaming helper (ADR-0020)."""

import json

from pydantic import BaseModel

from app.api.streaming import NDJSON_MEDIA_TYPE, ndjson_response, serialize_ndjson


class _Row(BaseModel):
    id: int
    name: str
    optional: str | None = None


def test_serialize_ndjson_emits_one_line_per_row():
    rows = [_Row(id=1, name="a"), _Row(id=2, name="b"), _Row(id=3, name="c")]
    payload = b"".join(serialize_ndjson(iter(rows)))

    lines = payload.split(b"\n")
    # Trailing newline produces an empty final element.
    assert lines[-1] == b""
    body_lines = lines[:-1]
    assert len(body_lines) == 3
    assert [json.loads(line) for line in body_lines] == [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
        {"id": 3, "name": "c"},
    ]


def test_serialize_ndjson_excludes_none():
    rows = [_Row(id=1, name="a", optional=None), _Row(id=2, name="b", optional="x")]
    payload = b"".join(serialize_ndjson(iter(rows)))

    parsed = [json.loads(line) for line in payload.splitlines() if line]
    assert parsed[0] == {"id": 1, "name": "a"}
    assert parsed[1] == {"id": 2, "name": "b", "optional": "x"}


def test_serialize_ndjson_handles_empty_iterator():
    assert b"".join(serialize_ndjson(iter([]))) == b""


def test_serialize_ndjson_is_lazy():
    """Generator does not materialise the source iterable up front."""
    consumed: list[int] = []

    def source():
        for i in range(5):
            consumed.append(i)
            yield _Row(id=i, name=str(i))

    gen = serialize_ndjson(source())
    # Pull only the first row's bytes (model + newline = 2 yields).
    next(gen)
    next(gen)
    assert consumed == [0]


def test_ndjson_response_uses_x_ndjson_media_type():
    response = ndjson_response(iter([_Row(id=1, name="a")]))
    assert response.media_type == NDJSON_MEDIA_TYPE
