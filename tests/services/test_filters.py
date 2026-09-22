import pytest

from app.services.exceptions import FDSValidationError
from app.services.filters import _value_candidates, parse_annotation


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("disruption", ("disruption", None)),
        ("confinement_mode:H-mode", ("confinement_mode", "H-mode")),
        # Split on the FIRST separator only, so a value may contain one.
        ("mode:n=1:tearing", ("mode", "n=1:tearing")),
        ("elm:type-I", ("elm", "type-I")),
    ],
)
def test_parse_annotation(raw: str, expected: tuple[str, str | None]):
    assert parse_annotation(raw) == expected


@pytest.mark.parametrize("raw", ["", ":", ":H-mode"])
def test_parse_annotation_rejects_missing_name(raw: str):
    with pytest.raises(FDSValidationError, match="Invalid annotation filter"):
        parse_annotation(raw)


def test_parse_annotation_rejects_empty_value():
    """A trailing separator is ambiguous: presence, or equality to empty string?"""
    with pytest.raises(FDSValidationError, match="value is expected"):
        parse_annotation("disruption:")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("H-mode", ["H-mode"]),
        ("true", ["true"]),
        ("FALSE", ["FALSE", "false"]),
        ("42", ["42"]),
        ("0.5", ["0.5"]),
        # A stored 1.50 reads back as "1.5", so both spellings have to match.
        ("1.50", ["1.50", "1.5"]),
        ("n=1 tearing", ["n=1 tearing"]),
    ],
)
def test_value_candidates(value: str, expected: list[str]):
    """Comparison happens on the JSON value as text, so candidates are text too."""
    assert _value_candidates(value) == expected


def test_value_candidates_always_keeps_the_raw_string():
    """So a property genuinely storing the string "true" still matches."""
    assert "true" in _value_candidates("true")
    assert "42" in _value_candidates("42")
