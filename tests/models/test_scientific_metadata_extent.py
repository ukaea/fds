import json

from app.core.db import _json_serializer
from app.models.scientific_metadata import Extent, ScientificProperty


def _roundtrip(prop: ScientificProperty) -> ScientificProperty:
    # Mirrors JSON-column persistence: serialise the list, reload as dicts,
    # then re-validate into the typed model.
    raw = json.loads(_json_serializer([prop]))
    return ScientificProperty.model_validate(raw[0])


def test_time_extent_roundtrips_to_typed_extent():
    prop = ScientificProperty(
        name="confinement_mode",
        value="H-mode",
        extent=Extent(dimension="time", start=1.0, end=2.0),
    )
    back = _roundtrip(prop)
    assert isinstance(back.extent, Extent)
    assert back.extent.dimension == "time"
    assert back.extent.start == 1.0
    assert back.extent.end == 2.0
    assert back.extent.unit is None


def test_scalar_property_roundtrips_with_no_extent():
    """Scalar properties (no extent) are unchanged; extent stays None."""
    prop = ScientificProperty(name="plasma_current", value=0.8, unit="MA")
    back = _roundtrip(prop)
    assert back.extent is None
    assert back.name == "plasma_current"
    assert back.value == 0.8
    assert back.unit == "MA"


def test_point_extent_roundtrips():
    """end=None (a point, e.g. a disruption time) survives the round-trip."""
    prop = ScientificProperty(
        name="disruption",
        value=True,
        extent=Extent(dimension="time", start=0.5),
    )
    back = _roundtrip(prop)
    assert back.extent is not None
    assert back.extent.start == 0.5
    assert back.extent.end is None


def test_non_time_extent_roundtrips_with_unit():
    """An extent on a non-time axis carries its dimension and unit."""
    prop = ScientificProperty(
        name="mode",
        value="n=1 tearing",
        extent=Extent(dimension="frequency", start=8000, end=12000, unit="Hz"),
    )
    back = _roundtrip(prop)
    assert back.extent is not None
    assert back.extent.dimension == "frequency"
    assert back.extent.start == 8000
    assert back.extent.end == 12000
    assert back.extent.unit == "Hz"


def test_negative_extent_roundtrips():
    """Coordinates may be negative, e.g. pre-trigger time."""
    prop = ScientificProperty(
        name="baseline",
        value=True,
        extent=Extent(dimension="time", start=-0.1, end=0.0),
    )
    back = _roundtrip(prop)
    assert back.extent is not None
    assert back.extent.start == -0.1
    assert back.extent.end == 0.0
