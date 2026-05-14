from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate
from app.models.policy import AccessLevel
from app.models.scientific_metadata import ScientificProperty
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
    assert ld["@type"] == "dcat:Dataset"
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
