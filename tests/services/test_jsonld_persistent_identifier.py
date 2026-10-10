import pytest

from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.shot import Shot
from app.models.source import Source, SourceKind
from app.services.jsonld import (
    map_collection_to_dcat,
    map_dataset_to_dcat,
    map_device_to_dcat,
    map_shot_to_dcat,
    map_source_to_dcat,
)
from tests.conftest import resource

BASE = "http://testserver"


def _dataset_node(pid: str | None) -> dict:
    return resource(
        map_dataset_to_dcat(Dataset(id=8, name="eq", persistent_identifier=pid), BASE)
    )


def test_compact_doi_is_published_as_its_resolver_uri():
    node = _dataset_node("doi:10.5072/fds.8")

    assert node["adms:identifier"] == {
        "@type": "adms:Identifier",
        "skos:notation": {
            "@value": "https://doi.org/10.5072/fds.8",
            "@type": "xsd:anyURI",
        },
    }


def test_absolute_uri_is_published_unchanged():
    node = _dataset_node("https://hdl.handle.net/21.T11998/abc")

    assert node["adms:identifier"]["skos:notation"]["@value"] == (
        "https://hdl.handle.net/21.T11998/abc"
    )


def test_unrecognised_form_is_published_as_given_not_as_a_link():
    node = _dataset_node("ark:/12345/x9")

    assert node["adms:identifier"]["skos:notation"] == "ark:/12345/x9"


def test_fds_identifier_stays_in_dct_identifier():
    node = _dataset_node("doi:10.5072/fds.8")

    assert node["identifier"] == "8"


def test_no_identifier_node_without_a_persistent_identifier():
    assert "adms:identifier" not in _dataset_node(None)


PID = "doi:10.5072/fds.x"


@pytest.mark.parametrize(
    "document",
    [
        lambda: map_device_to_dcat(
            Device(name="mast", persistent_identifier=PID), BASE
        ),
        lambda: map_shot_to_dcat(
            Shot(id="1", device_name="mast", persistent_identifier=PID), BASE
        ),
        lambda: map_collection_to_dcat(
            Collection(id=3, name="c", persistent_identifier=PID),
            BASE,
            datasets=[],
            child_collections=[],
        ),
        lambda: map_source_to_dcat(
            Source(
                id=1, name="efit", kind=SourceKind.SOFTWARE, persistent_identifier=PID
            ),
            BASE,
        ),
        lambda: map_source_to_dcat(
            Source(
                id=6,
                name="thomson",
                kind=SourceKind.INSTRUMENT,
                persistent_identifier=PID,
            ),
            BASE,
        ),
    ],
    ids=["device", "shot", "collection", "agent", "instrument"],
)
def test_every_citable_record_publishes_its_identifier(document):
    node = document()
    if "@graph" in node:
        node = resource(node)

    assert node["adms:identifier"]["skos:notation"]["@value"] == (
        "https://doi.org/10.5072/fds.x"
    )
