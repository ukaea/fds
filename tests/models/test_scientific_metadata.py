import json

import pytest
from pydantic import ValidationError

from app.core.db import _json_serializer
from app.models.scientific_metadata import Extent, MetadataKind, ScientificProperty


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


def test_a_group_roundtrips_with_the_properties_inside_it():
    """Stored metadata keeps every field, so a group comes back with "value": null."""
    prop = ScientificProperty(
        name="coolant",
        description="The water loop cooling the sample.",
        properties=[
            ScientificProperty(name="type", value="water"),
            ScientificProperty(
                name="thermocouple",
                properties=[
                    ScientificProperty(name="id", value="T1"),
                    ScientificProperty(name="max", value=850, unit="°C"),
                ],
            ),
        ],
    )
    back = _roundtrip(prop)
    assert back == prop
    assert back.properties is not None
    assert back.properties[1].properties is not None
    assert back.properties[1].properties[1].value == 850


def test_a_group_with_an_extent_covers_the_properties_inside_it():
    prop = ScientificProperty(
        name="elm",
        extent=Extent(dimension="time", start=0.20, end=0.45, unit="s"),
        properties=[
            ScientificProperty(name="count", value=14),
            ScientificProperty(name="frequency", value=56, unit="Hz"),
        ],
    )
    assert _roundtrip(prop) == prop


def test_a_null_value_is_a_value():
    assert (
        ScientificProperty.model_validate({"name": "gas", "value": None}).value is None
    )


def test_a_property_with_neither_a_value_nor_properties_is_rejected():
    with pytest.raises(ValidationError, match="needs a value"):
        ScientificProperty.model_validate({"name": "gas"})


def test_an_object_value_is_rejected():
    with pytest.raises(ValidationError, match="group of properties"):
        ScientificProperty.model_validate(
            {"name": "coolant", "value": {"type": "water"}}
        )


def test_a_list_value_is_rejected():
    with pytest.raises(ValidationError, match="several properties"):
        ScientificProperty.model_validate({"name": "elm_times", "value": [0.2, 0.3]})


def test_a_name_containing_a_dot_is_rejected():
    with pytest.raises(ValidationError, match="contains '.'"):
        ScientificProperty(name="coolant.type", value="water")


def test_a_name_containing_a_colon_is_rejected():
    with pytest.raises(ValidationError, match="contains ':'"):
        ScientificProperty(name="mode:n", value=1)


def test_a_group_needs_at_least_one_property():
    with pytest.raises(ValidationError, match="at least 1 item"):
        ScientificProperty(name="coolant", properties=[])


def test_a_group_cannot_have_a_value():
    with pytest.raises(ValidationError, match="cannot have a value"):
        ScientificProperty(
            name="coolant",
            value="water",
            properties=[ScientificProperty(name="type", value="water")],
        )


def test_a_group_cannot_have_a_unit_or_kind():
    with pytest.raises(ValidationError, match="cannot have a unit or kind"):
        ScientificProperty(
            name="thermocouple",
            unit="°C",
            kind=MetadataKind.QUANTITY,
            properties=[ScientificProperty(name="max", value=850)],
        )


def test_a_property_inside_a_group_cannot_have_an_extent():
    with pytest.raises(ValidationError, match=r"extent of their own \(count\)"):
        ScientificProperty(
            name="elm",
            properties=[
                ScientificProperty(
                    name="count",
                    value=14,
                    extent=Extent(dimension="time", start=0.20, end=0.45),
                )
            ],
        )
