from datetime import date

import pytest

from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.shot import Shot
from app.services.jsonld import (
    map_collection_to_dcat,
    map_dataset_to_dcat,
    map_shot_to_dcat,
)
from tests.conftest import record, resource

BASE = "http://testserver"
PUBLISHED = date(2024, 3, 1)


@pytest.mark.parametrize(
    "document",
    [
        lambda: map_dataset_to_dcat(Dataset(id=8, name="eq", issued=PUBLISHED), BASE),
        lambda: map_shot_to_dcat(
            Shot(id="1", device_name="mast", issued=PUBLISHED), BASE
        ),
        lambda: map_collection_to_dcat(
            Collection(id=3, name="c", issued=PUBLISHED),
            BASE,
            datasets=[],
            child_collections=[],
        ),
    ],
    ids=["dataset", "shot", "collection"],
)
def test_publication_date_is_the_resource_s_own_issued(document):
    published = document()

    assert resource(published)["dct:issued"] == {
        "@value": "2024-03-01",
        "@type": "xsd:date",
    }
    assert record(published).get("issued") != "2024-03-01"


def test_no_issued_without_a_publication_date():
    node = resource(map_dataset_to_dcat(Dataset(id=8, name="eq"), BASE))

    assert "dct:issued" not in node
