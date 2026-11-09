import pytest

from app.services.exceptions import FDSValidationError
from app.services.filters import _value_candidates, parse_property


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
def test_parse_property(raw: str, expected: tuple[str, str | None]):
    assert parse_property(raw) == expected


@pytest.mark.parametrize("raw", ["", ":", ":H-mode"])
def test_parse_property_rejects_missing_name(raw: str):
    with pytest.raises(FDSValidationError, match="Invalid property filter"):
        parse_property(raw)


def test_parse_property_rejects_empty_value():
    """A trailing separator is ambiguous: presence, or equality to empty string?"""
    with pytest.raises(FDSValidationError, match="value is expected"):
        parse_property("disruption:")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("H-mode", ['"H-mode"']),
        ("true", ['"true"', "true"]),
        ("FALSE", ['"FALSE"', "false"]),
        ("42", ['"42"', "42"]),
        ("0.5", ['"0.5"', "0.5"]),
        ("1e-05", ['"1e-05"', "0.00001"]),
        # JSON has no leading zeros.
        ("042", ['"042"', "42"]),
        ("n=1 tearing", ['"n=1 tearing"']),
        ('say "hi"', ['"say \\"hi\\""']),
        # At PostgreSQL's numeric limits, and past them, where casting would fail
        # the query.
        ("1e131071", ['"1e131071"', "1E+131071"]),
        ("1e131072", ['"1e131072"']),
        ("1e-16383", ['"1e-16383"', "1E-16383"]),
        ("1e-16384", ['"1e-16384"']),
        ("1.5e-16383", ['"1.5e-16383"']),
    ],
)
def test_value_candidates(value: str, expected: list[str]):
    """The string itself, then the boolean or number it spells, as JSON."""
    assert _value_candidates(value) == expected
