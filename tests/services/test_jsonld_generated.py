from datetime import UTC, datetime

from app.models.activity import Activity
from app.models.collection import Collection
from app.models.dataset import Dataset
from app.services.jsonld import map_collection_to_dcat, map_dataset_to_dcat
from tests.conftest import resource

BASE = "http://testserver"
RUN_ENDED = datetime(2026, 9, 23, 9, 16, 37, tzinfo=UTC)


def test_dataset_was_generated_when_its_activity_ended():
    dataset = Dataset(id=8, name="eq", activity=Activity(id=1, ended_at=RUN_ENDED))

    node = resource(map_dataset_to_dcat(dataset, BASE))

    assert node["prov:generatedAtTime"] == {
        "@value": RUN_ENDED.isoformat(),
        "@type": "xsd:dateTime",
    }


def test_collection_was_generated_when_its_activity_ended():
    collection = Collection(id=3, name="c", activity=Activity(id=1, ended_at=RUN_ENDED))

    node = resource(
        map_collection_to_dcat(collection, BASE, datasets=[], child_collections=[])
    )

    assert node["prov:generatedAtTime"]["@value"] == RUN_ENDED.isoformat()


def test_no_generation_time_without_an_ended_activity():
    running = Dataset(id=8, name="eq", activity=Activity(id=1))

    assert "prov:generatedAtTime" not in resource(map_dataset_to_dcat(running, BASE))
    assert "prov:generatedAtTime" not in resource(
        map_dataset_to_dcat(Dataset(id=9, name="eq"), BASE)
    )
