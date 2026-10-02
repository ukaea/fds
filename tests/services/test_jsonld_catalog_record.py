from datetime import UTC, datetime

from app.models.device import Device
from app.models.shot import Shot
from app.services.jsonld import device_node, map_device_to_dcat, map_shot_to_dcat
from tests.conftest import record, resource

BASE = "http://testserver"
FIRED = datetime(2012, 1, 27, 15, 52, tzinfo=UTC)
LISTED = datetime(2026, 9, 28, 13, 55, 58, tzinfo=UTC)
EDITED = datetime(2026, 10, 1, 15, 46, 7, tzinfo=UTC)


def _shot() -> Shot:
    return Shot(
        id="28352",
        device_name="mast",
        shot_at=FIRED,
        created_at=LISTED,
        updated_at=EDITED,
    )


def test_shot_carries_only_when_it_happened():
    shot = resource(map_shot_to_dcat(_shot(), BASE))

    assert "created" not in shot
    assert "modified" not in shot
    assert shot["dct:temporal"]["startDate"] == FIRED.isoformat()


def test_record_carries_when_fds_listed_and_edited_the_shot():
    document = map_shot_to_dcat(_shot(), BASE)
    shot, entry = resource(document), record(document)

    assert entry["@id"] == f"{shot['@id']}#record"
    assert entry["foaf:primaryTopic"] == {"@id": shot["@id"]}
    assert entry["issued"] == LISTED.isoformat()
    assert entry["modified"] == EDITED.isoformat()
    assert document["@context"]["issued"]["@id"] == "dct:issued"


def test_embedded_device_node_has_no_record():
    device = Device(name="mast", created_at=LISTED, updated_at=EDITED)

    node = device_node(device, BASE)

    assert "@graph" not in node
    assert "modified" not in node
    assert resource(map_device_to_dcat(device, BASE))["@id"] == node["@id"]
