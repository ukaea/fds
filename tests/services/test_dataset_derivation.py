import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.activity import Activity, ActivityCreate, ActivityType
from app.models.dataset import (
    Dataset,
    DatasetCreate,
    DatasetDerivation,
    DatasetDerivationCreate,
)
from app.models.policy import AccessLevel
from app.models.source import SourceCreate, SourceKind
from app.services.activity_service import ActivityService
from app.services.dataset_service import DatasetService
from app.services.exceptions import (
    ConflictError,
    FDSValidationError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.services.jsonld import map_dataset_to_dcat
from app.services.source_service import SourceService

admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
BASE = "http://testserver"


def _dataset(session: Session, name: str, **kwargs) -> Dataset:
    return DatasetService(session).create(
        DatasetCreate(name=name, level=0, **kwargs), user=admin
    )


def _dataset_id(session: Session, name: str, **kwargs) -> int:
    """A dataset's id, for the many cases that only need to point at one."""
    dataset = _dataset(session, name, **kwargs)
    assert dataset.id is not None
    return dataset.id


def _id(obj: Dataset | Activity | DatasetDerivation) -> int:
    assert obj.id is not None
    return obj.id


def _analysis_activity(session: Session) -> Activity:
    source = SourceService(session).create(
        SourceCreate(name="code", kind=SourceKind.SOFTWARE), user=admin
    )
    return ActivityService(session).create(
        ActivityCreate(source_id=source.id, activity_type=ActivityType.ANALYSIS),
        user=admin,
    )


def test_derive_from_registered_dataset(session: Session):
    upstream_id = _dataset_id(session, "raw")
    derived = _dataset(
        session,
        "processed",
        derived_from=[DatasetDerivationCreate(source_dataset_id=upstream_id)],
    )

    links = DatasetService(session).get_derivations(_id(derived), admin)
    assert [link.source_dataset_id for link in links] == [upstream_id]

    node = map_dataset_to_dcat(derived, BASE)["prov:wasDerivedFrom"][0]
    assert node["@id"] == f"{BASE}/v1/datasets/{upstream_id}"
    assert node["@type"] == "prov:Entity"


@pytest.mark.parametrize(
    ("identifier", "expected_id"),
    [
        # DOI in every form people paste
        ("10.5281/zenodo.123", "https://doi.org/10.5281/zenodo.123"),
        ("doi:10.5281/zenodo.123", "https://doi.org/10.5281/zenodo.123"),
        ("https://doi.org/10.5281/zenodo.123", "https://doi.org/10.5281/zenodo.123"),
        # any URL passes through untouched
        ("https://huggingface.co/datasets/x", "https://huggingface.co/datasets/x"),
        # other PIDs with a single canonical resolver
        ("hdl:20.500.12345/abc", "https://hdl.handle.net/20.500.12345/abc"),
        (
            "swh:1:dir:0f1a2b3c",
            "https://archive.softwareheritage.org/swh:1:dir:0f1a2b3c",
        ),
        # already an absolute IRI: an @id identifies, it need not dereference
        ("urn:nbn:de:bvb:19-146642", "urn:nbn:de:bvb:19-146642"),
    ],
)
def test_external_identifier_becomes_id(
    session: Session, identifier: str, expected_id: str
):
    """A DOI given bare, prefixed, or as a URL all resolve to the same @id."""
    derived = _dataset(
        session,
        "processed",
        derived_from=[
            DatasetDerivationCreate(source_identifier=identifier, source_label="Zen")
        ],
    )
    node = map_dataset_to_dcat(derived, BASE)["prov:wasDerivedFrom"][0]
    assert node["@id"] == expected_id
    assert node["dct:title"] == "Zen"


@pytest.mark.parametrize(
    "identifier",
    [
        "internal-ref-42",
        # a bare Handle is ambiguous with other prefix/suffix identifiers, so it
        # needs the hdl: prefix; only DOI's "10." range is unambiguous
        "20.500.12345/abc",
        "2381/12345",
        # ARK has no canonical resolver host, only conventions
        "ark:/12345/abc",
        # an unregistered scheme must not be promoted on the strength of a colon
        "IGSN:IECUR0098",
    ],
)
def test_unresolvable_identifier_is_not_an_id(session: Session, identifier: str):
    """An identifier we cannot turn into a URI must not masquerade as one."""
    derived = _dataset(
        session,
        "processed",
        derived_from=[DatasetDerivationCreate(source_identifier=identifier)],
    )
    node = map_dataset_to_dcat(derived, BASE)["prov:wasDerivedFrom"][0]
    assert "@id" not in node
    assert node["dct:identifier"] == identifier


def test_description_only_upstream_is_a_blank_node(session: Session):
    """The weakest honest assertion: named but unidentifiable."""
    derived = _dataset(
        session,
        "processed",
        derived_from=[
            DatasetDerivationCreate(
                source_label="Legacy tape",
                source_description="Recovered from a 1998 archive tape, no PID",
            )
        ],
    )
    node = map_dataset_to_dcat(derived, BASE)["prov:wasDerivedFrom"][0]
    assert "@id" not in node
    assert "dct:identifier" not in node
    assert node["dct:title"] == "Legacy tape"
    assert node["@type"] == "prov:Entity"


def test_qualified_derivation_names_the_activity(session: Session):
    upstream_id = _dataset_id(session, "raw")
    activity = _analysis_activity(session)
    derived = _dataset(
        session,
        "processed",
        activity_id=_id(activity),
        derived_from=[DatasetDerivationCreate(source_dataset_id=upstream_id)],
    )
    session.refresh(derived)

    doc = map_dataset_to_dcat(derived, BASE)
    qualified = doc["prov:qualifiedDerivation"][0]
    assert qualified["prov:hadActivity"]["@id"].endswith(f"/activities/{_id(activity)}")
    assert qualified["prov:entity"]["@id"].endswith(f"/datasets/{upstream_id}")


def test_no_derivations_emits_nothing(session: Session):
    """Absence must stay absent: an unstated derivation is not an empty claim."""
    derived = _dataset(session, "standalone")
    doc = map_dataset_to_dcat(derived, BASE)
    assert "prov:wasDerivedFrom" not in doc
    assert "prov:qualifiedDerivation" not in doc


def test_self_derivation_rejected(session: Session):
    derived = _dataset(session, "processed")
    with pytest.raises(FDSValidationError, match="cannot be derived from itself"):
        DatasetService(session).add_derivation(
            dataset_id=_id(derived),
            obj_in=DatasetDerivationCreate(source_dataset_id=_id(derived)),
            user=admin,
        )


def test_missing_upstream_dataset_rejected(session: Session):
    derived = _dataset(session, "processed")
    with pytest.raises(ResourceNotFoundError):
        DatasetService(session).add_derivation(
            dataset_id=_id(derived),
            obj_in=DatasetDerivationCreate(source_dataset_id=9999),
            user=admin,
        )


def test_add_and_remove_derivation(session: Session):
    service = DatasetService(session)
    upstream_id = _dataset_id(session, "raw")
    derived = _dataset(session, "processed")

    link = service.add_derivation(
        dataset_id=_id(derived),
        obj_in=DatasetDerivationCreate(source_dataset_id=upstream_id),
        user=admin,
    )
    assert len(service.get_derivations(_id(derived), admin)) == 1

    service.remove_derivation(
        dataset_id=_id(derived), derivation_id=_id(link), user=admin
    )
    assert service.get_derivations(_id(derived), admin) == []


def test_remove_derivation_belonging_to_another_dataset(session: Session):
    """A derivation id from a different dataset must not be removable here."""
    service = DatasetService(session)
    upstream_id = _dataset_id(session, "raw")
    a = _dataset(session, "a")
    b = _dataset(session, "b")
    link = service.add_derivation(
        dataset_id=_id(a),
        obj_in=DatasetDerivationCreate(source_dataset_id=upstream_id),
        user=admin,
    )
    with pytest.raises(ResourceNotFoundError):
        service.remove_derivation(
            dataset_id=_id(b), derivation_id=_id(link), user=admin
        )


def test_upstream_need_not_be_an_activity_input(session: Session):
    """Deliberate: derivation crosses runs, so no subset check against inputs."""
    unrelated_id = _dataset_id(session, "unrelated")
    activity = _analysis_activity(session)
    derived = _dataset(
        session,
        "processed",
        activity_id=_id(activity),
        derived_from=[DatasetDerivationCreate(source_dataset_id=unrelated_id)],
    )
    assert len(DatasetService(session).get_derivations(_id(derived), admin)) == 1


def _derive(session: Session, dataset: Dataset, upstream_id: int) -> None:
    """Assert that ``dataset`` was derived from a registered upstream."""
    DatasetService(session).add_derivation(
        dataset_id=_id(dataset),
        obj_in=DatasetDerivationCreate(source_dataset_id=upstream_id),
        user=admin,
    )


def test_lineage_walks_a_chain_transitively(session: Session):
    """The point of the endpoint: `derivations` gives one hop, lineage gives all."""
    raw_id = _dataset_id(session, "raw")
    intermediate = _dataset(
        session,
        "calibrated",
        derived_from=[DatasetDerivationCreate(source_dataset_id=raw_id)],
    )
    final = _dataset(
        session,
        "profile",
        derived_from=[DatasetDerivationCreate(source_dataset_id=_id(intermediate))],
    )

    lineage = DatasetService(session).get_lineage(_id(final), admin)

    assert lineage.dataset_id == _id(final)
    assert [node.name for node in lineage.derived_from] == ["calibrated"]
    assert [n.name for n in lineage.derived_from[0].derived_from] == ["raw"]


def test_lineage_leaves_external_upstreams_unexpanded(session: Session):
    derived = _dataset(
        session,
        "processed",
        derived_from=[
            DatasetDerivationCreate(
                source_identifier="10.5281/zenodo.123", source_label="On Zenodo"
            ),
            DatasetDerivationCreate(source_description="Recovered from a 1998 tape"),
        ],
    )

    lineage = DatasetService(session).get_lineage(_id(derived), admin)

    identified, described = lineage.derived_from
    assert identified.identifier == "10.5281/zenodo.123"
    assert identified.label == "On Zenodo"
    assert identified.dataset_id is None and identified.derived_from == []
    assert described.description == "Recovered from a 1998 tape"


def test_lineage_expands_a_shared_ancestor_once(session: Session):
    """A diamond: the shared ancestor expands on the first path, stubs on the second."""
    root_id = _dataset_id(session, "root")
    left = _dataset(
        session,
        "left",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )
    right = _dataset(
        session,
        "right",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )
    top = _dataset(session, "top")
    _derive(session, top, _id(left))
    _derive(session, top, _id(right))

    lineage = DatasetService(session).get_lineage(_id(top), admin)

    first, second = lineage.derived_from
    assert [n.name for n in first.derived_from] == ["root"]
    assert first.derived_from[0].seen is None
    assert second.derived_from[0].dataset_id == root_id
    assert second.derived_from[0].seen is True
    assert second.derived_from[0].name is None


def test_lineage_terminates_on_a_cycle(session: Session):
    """The walk survives a cycle without relying on validation to prevent one.

    The service now refuses the closing edge, so this writes it directly. Rows
    can predate the check or arrive by a path that does not go through the
    service, and a walk that recursed forever on such data would be a worse
    failure than the data itself.
    """
    a = _dataset(session, "a")
    b = _dataset(
        session, "b", derived_from=[DatasetDerivationCreate(source_dataset_id=_id(a))]
    )
    session.add(DatasetDerivation(dataset_id=_id(a), source_dataset_id=_id(b)))
    session.commit()  # closes the loop: a <- b <- a

    lineage = DatasetService(session).get_lineage(_id(a), admin)

    back_reference = lineage.derived_from[0].derived_from[0]
    assert back_reference.dataset_id == _id(a)
    assert back_reference.seen is True


def test_deleting_an_asserted_upstream_is_refused(session: Session):
    """Provenance outranks tidiness: an upstream with dependants stays.

    Nothing else protects the claim. The foreign key would reject the delete
    with a database error; the service refuses it with an explanation naming
    what depends on it.
    """
    upstream = _dataset(session, "raw")
    upstream_id = _id(upstream)
    derived = _dataset(
        session,
        "processed",
        derived_from=[DatasetDerivationCreate(source_dataset_id=upstream_id)],
    )

    with pytest.raises(ConflictError, match=str(_id(derived))):
        DatasetService(session).delete(upstream_id, admin)

    assert session.get(Dataset, upstream_id) is not None


def test_lineage_withholds_an_upstream_the_caller_cannot_read(session: Session):
    """A restricted upstream is acknowledged but not described, and not walked past.

    Its id is already visible through the derivations listing, so naming it adds
    nothing; its name and its own upstreams would be new leakage.
    """
    secret_root_id = _dataset_id(session, "secret_root")
    secret = _dataset(
        session,
        "secret",
        access_level=AccessLevel.RESTRICTED,
        derived_from=[DatasetDerivationCreate(source_dataset_id=secret_root_id)],
    )
    public = _dataset(
        session,
        "public",
        access_level=AccessLevel.PUBLIC,
        derived_from=[DatasetDerivationCreate(source_dataset_id=_id(secret))],
    )

    anonymous = AuthenticatedUser(id="nobody", scopes=())
    lineage = DatasetService(session).get_lineage(_id(public), anonymous)

    withheld = lineage.derived_from[0]
    assert withheld.dataset_id == _id(secret)
    assert withheld.restricted is True
    assert withheld.name is None
    assert withheld.derived_from == []


def test_lineage_refuses_a_dataset_the_caller_cannot_read(session: Session):
    restricted = _dataset(session, "restricted", access_level=AccessLevel.RESTRICTED)
    anonymous = AuthenticatedUser(id="nobody", scopes=())

    with pytest.raises(ForbiddenError):
        DatasetService(session).get_lineage(_id(restricted), anonymous)


def test_lineage_of_a_missing_dataset_is_not_found(session: Session):
    with pytest.raises(ResourceNotFoundError):
        DatasetService(session).get_lineage(9999, admin)


def test_derivation_cycle_is_rejected(session: Session):
    """B derives from A, so A cannot then be said to derive from B."""
    a = _dataset(session, "a")
    b = _dataset(
        session, "b", derived_from=[DatasetDerivationCreate(source_dataset_id=_id(a))]
    )

    with pytest.raises(FDSValidationError, match="already derives from"):
        _derive(session, a, _id(b))


def test_longer_derivation_cycle_is_rejected(session: Session):
    """The check follows the whole chain, not just the immediate upstream."""
    a = _dataset(session, "a")
    b = _dataset(
        session, "b", derived_from=[DatasetDerivationCreate(source_dataset_id=_id(a))]
    )
    c = _dataset(
        session, "c", derived_from=[DatasetDerivationCreate(source_dataset_id=_id(b))]
    )

    with pytest.raises(FDSValidationError, match="already derives from"):
        _derive(session, a, _id(c))  # a <- c <- b <- a


def test_a_shared_ancestor_is_not_a_cycle(session: Session):
    """Two paths to one ancestor is a diamond, which is ordinary and allowed."""
    root_id = _dataset_id(session, "root")
    left = _dataset(
        session,
        "left",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )
    right = _dataset(
        session,
        "right",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )
    top = _dataset(session, "top")

    _derive(session, top, _id(left))
    _derive(session, top, _id(right))

    assert len(DatasetService(session).get_derivations(_id(top), admin)) == 2


def test_deriving_from_a_downstream_sibling_is_allowed(session: Session):
    """Sharing an ancestor does not make two datasets each other's ancestor."""
    root_id = _dataset_id(session, "root")
    first = _dataset(
        session,
        "first",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )
    second = _dataset(
        session,
        "second",
        derived_from=[DatasetDerivationCreate(source_dataset_id=root_id)],
    )

    _derive(session, second, _id(first))  # second <- first, both <- root

    assert len(DatasetService(session).get_derivations(_id(second), admin)) == 2
