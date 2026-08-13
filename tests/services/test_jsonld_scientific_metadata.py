from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.policy import AccessLevel
from app.models.scientific_metadata import Extent, ScientificProperty
from app.models.shot import Shot
from app.services.dataset_service import DatasetService
from app.services.jsonld import (
    _map_scientific_metadata_to_jsonld,
    map_dataset_to_dcat,
    map_shot_to_dcat,
)

admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
BASE = "http://testserver"


def test_scientific_metadata_helper_with_dicts():
    raw = [
        {"name": "plasma_current", "value": 0.8, "unit": "MA"},
        {"name": "confinement_mode", "value": "H-mode"},
        {"name": "disrupted", "value": False, "description": "no disruption"},
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    assert len(result) == 3
    assert result[0]["@type"] == "schema:PropertyValue"
    assert result[0]["schema:name"] == "plasma_current"
    assert result[0]["schema:value"] == 0.8
    assert result[0]["schema:unitText"] == "MA"
    assert "schema:description" not in result[0]
    assert result[1]["schema:name"] == "confinement_mode"
    assert result[2]["schema:description"] == "no disruption"


def test_scientific_metadata_helper_with_objects():
    props = [
        ScientificProperty(name="ip", value=1.2, unit="MA"),
        ScientificProperty(name="mode", value="L-mode"),
    ]
    result = _map_scientific_metadata_to_jsonld(props)
    assert result[0]["schema:value"] == 1.2
    assert result[0]["schema:unitText"] == "MA"
    assert result[1]["schema:name"] == "mode"
    assert "schema:unitText" not in result[1]


def test_map_dataset_to_dcat_includes_scientific_metadata(session):
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="sci-test",
            level=1,
            url="s3://bucket/sci",
            access_level=AccessLevel.PUBLIC,
            scientific_metadata=[
                ScientificProperty(name="plasma_current", value=0.8, unit="MA"),
                ScientificProperty(name="disrupted", value=False),
            ],
        ),
        user=admin,
    )
    session.commit()

    ld = map_dataset_to_dcat(dataset, BASE)
    props = ld.get("schema:additionalProperty")
    assert props is not None
    assert len(props) == 2
    assert props[0]["schema:name"] == "plasma_current"
    assert props[0]["schema:value"] == 0.8
    assert props[0]["schema:unitText"] == "MA"
    assert props[1]["schema:name"] == "disrupted"
    assert props[1]["schema:value"] is False


def test_map_dataset_to_dcat_no_scientific_metadata(session):
    dataset = DatasetService(session).create(
        DatasetCreate(
            name="plain-test",
            level=1,
            url="s3://bucket/plain",
            access_level=AccessLevel.PUBLIC,
        ),
        user=admin,
    )
    session.commit()
    ld = map_dataset_to_dcat(dataset, BASE)
    assert "schema:additionalProperty" not in ld


def test_map_shot_to_dcat_includes_scientific_metadata():
    shot = Shot(
        id="30420",
        device_name="MAST",
        scientific_metadata=[
            ScientificProperty(name="plasma_current", value=0.8, unit="MA"),
            ScientificProperty(name="confinement_mode", value="H-mode"),
        ],
    )
    ld = map_shot_to_dcat(shot, BASE)
    assert ld["@type"] == "dcat:Catalog"
    assert ld["@id"] == f"{BASE}/api/v1/devices/MAST/shots/30420"
    props = ld.get("schema:additionalProperty")
    assert props is not None
    assert len(props) == 2
    assert props[0]["schema:name"] == "plasma_current"
    assert props[1]["schema:name"] == "confinement_mode"


def test_schema_namespace_in_context():
    shot = Shot(id="1", device_name="D")
    ld = map_shot_to_dcat(shot, BASE)
    assert ld["@context"]["schema"] == "https://schema.org/"


def test_scientific_metadata_helper_emits_time_extent_from_object():
    """A time-axis extent emits a W3C Time interval node under time:hasTime."""
    props = [
        ScientificProperty(
            name="confinement_mode",
            value="H-mode",
            extent=Extent(dimension="time", start=1.0, end=2.0, unit="s"),
        )
    ]
    result = _map_scientific_metadata_to_jsonld(props)
    interval = result[0]["time:hasTime"]
    assert interval["@type"] == "time:Interval"

    beginning = interval["time:hasBeginning"]
    assert beginning["@type"] == "time:Instant"
    begin_pos = beginning["time:inTimePosition"]
    assert begin_pos["@type"] == "time:TimePosition"
    assert begin_pos["time:numericPosition"] == 1.0
    assert begin_pos["time:unitType"] == {"@id": "time:unitSecond"}

    end_pos = interval["time:hasEnd"]["time:inTimePosition"]
    assert end_pos["time:numericPosition"] == 2.0
    assert end_pos["time:unitType"] == {"@id": "time:unitSecond"}


def test_scientific_metadata_helper_emits_time_extent_from_dict():
    raw = [
        {
            "name": "disruption",
            "value": True,
            "extent": {"dimension": "time", "start": 0.5, "unit": "s"},
        }
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    interval = result[0]["time:hasTime"]
    assert interval["@type"] == "time:Interval"
    begin_pos = interval["time:hasBeginning"]["time:inTimePosition"]
    assert begin_pos["time:numericPosition"] == 0.5
    assert begin_pos["time:unitType"] == {"@id": "time:unitSecond"}
    # end is None (a point) -> no time:hasEnd
    assert "time:hasEnd" not in interval


def test_scientific_metadata_helper_time_no_unit_omits_unit_type():
    """A time extent with no unit emits a numeric position but no unit type."""
    raw = [
        {
            "name": "disruption",
            "value": True,
            "extent": {"dimension": "time", "start": 3.4},
        }
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    begin_pos = result[0]["time:hasTime"]["time:hasBeginning"]["time:inTimePosition"]
    assert begin_pos["time:numericPosition"] == 3.4
    assert "time:unitType" not in begin_pos
    assert "schema:unitText" not in begin_pos


def test_scientific_metadata_helper_non_second_unit_falls_back():
    """A sub-second unit (no W3C Time individual) falls back to schema:unitText."""
    raw = [
        {
            "name": "elm",
            "value": True,
            "extent": {"dimension": "time", "start": 12.0, "unit": "ms"},
        }
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    begin_pos = result[0]["time:hasTime"]["time:hasBeginning"]["time:inTimePosition"]
    assert begin_pos["time:numericPosition"] == 12.0
    assert "time:unitType" not in begin_pos
    assert begin_pos["schema:unitText"] == "ms"


def test_scientific_metadata_helper_non_second_w3c_unit_is_typed():
    """A non-second unit that W3C Time *does* define maps to its individual."""
    raw = [
        {
            "name": "flat_top",
            "value": True,
            "extent": {"dimension": "time", "start": 3.0, "unit": "h"},
        }
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    begin_pos = result[0]["time:hasTime"]["time:hasBeginning"]["time:inTimePosition"]
    assert begin_pos["time:unitType"] == {"@id": "time:unitHour"}
    assert "schema:unitText" not in begin_pos


def test_scientific_metadata_helper_non_time_extent_is_numeric_range():
    """A non-time extent projects to a numeric range under schema:valueReference."""
    props = [
        ScientificProperty(
            name="mode",
            value="n=1 tearing",
            extent=Extent(dimension="frequency", start=8000, end=12000, unit="Hz"),
        )
    ]
    result = _map_scientific_metadata_to_jsonld(props)
    assert "time:hasTime" not in result[0]
    ref = result[0]["schema:valueReference"]
    assert ref["@type"] == "schema:PropertyValue"
    assert ref["schema:name"] == "frequency"
    assert ref["schema:minValue"] == 8000
    assert ref["schema:maxValue"] == 12000
    assert ref["schema:unitText"] == "Hz"


def test_scientific_metadata_helper_non_time_point_uses_value():
    """A non-time point extent (end None) uses schema:value, not min/max."""
    raw = [
        {
            "name": "spot",
            "value": True,
            "extent": {"dimension": "x", "start": 128, "unit": "px"},
        }
    ]
    result = _map_scientific_metadata_to_jsonld(raw)
    ref = result[0]["schema:valueReference"]
    assert ref["schema:value"] == 128
    assert "schema:minValue" not in ref
    assert ref["schema:unitText"] == "px"


def test_scientific_metadata_helper_omits_extent_when_absent():
    """Scalar properties (no extent) are unchanged; no localisation keys."""
    props = [ScientificProperty(name="plasma_current", value=0.8, unit="MA")]
    result = _map_scientific_metadata_to_jsonld(props)
    assert "time:hasTime" not in result[0]
    assert "schema:valueReference" not in result[0]


def test_time_namespace_in_context():
    shot = Shot(id="1", device_name="D")
    ld = map_shot_to_dcat(shot, BASE)
    assert ld["@context"]["time"] == "http://www.w3.org/2006/time#"


def test_shot_is_a_catalog_carrying_no_distribution():
    """A shot groups data, it does not hold any.

    ``dcat:Catalog`` is a kind of ``dcat:Dataset`` in DCAT 3, so a shot keeps
    every field it had before. What it must not have is a distribution, because
    a shot has nothing to download.
    """
    shot = Shot(id="30420", device_name="MAST", creator="MAST Team")

    ld = map_shot_to_dcat(shot, BASE)

    assert ld["@type"] == "dcat:Catalog"
    assert "dcat:distribution" not in ld
    # There can be any number of datasets in a shot, so they are not listed here.
    assert "dcat:dataset" not in ld
    # Properties valid on a Dataset remain valid on a Catalog.
    assert ld["creator"] == "MAST Team"
