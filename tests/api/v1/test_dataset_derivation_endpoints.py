from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.dataset import DatasetCreate, DatasetDerivationCreate
from app.models.device import DeviceCreate
from app.models.policy import AccessLevel
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService


def _create_dataset(client: TestClient, token: dict, name: str, **body) -> int:
    resp = client.post(
        "/v1/datasets/",
        headers=token,
        json={"name": name, "level": 1, **body},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_declare_derivation_inline_on_create(
    test_client: TestClient, admin_user_token: dict
):
    upstream = _create_dataset(test_client, admin_user_token, "raw")
    derived = _create_dataset(
        test_client,
        admin_user_token,
        "processed",
        derived_from=[{"source_dataset_id": upstream}],
    )

    resp = test_client.get(f"/v1/datasets/{derived}/derivations")
    assert resp.status_code == 200
    assert [d["source_dataset_id"] for d in resp.json()] == [upstream]


def test_derivation_lifecycle_via_endpoints(
    test_client: TestClient, admin_user_token: dict
):
    derived = _create_dataset(test_client, admin_user_token, "processed")

    resp = test_client.post(
        f"/v1/datasets/{derived}/derivations",
        headers=admin_user_token,
        json={
            "source_identifier": "10.5281/zenodo.123",
            "source_label": "Upstream on Zenodo",
        },
    )
    assert resp.status_code == 201, resp.text
    derivation_id = resp.json()["id"]
    assert resp.json()["source_identifier"] == "10.5281/zenodo.123"

    assert len(test_client.get(f"/v1/datasets/{derived}/derivations").json()) == 1

    resp = test_client.delete(
        f"/v1/datasets/{derived}/derivations/{derivation_id}",
        headers=admin_user_token,
    )
    assert resp.status_code == 204
    assert test_client.get(f"/v1/datasets/{derived}/derivations").json() == []


def test_empty_derivation_is_rejected(test_client: TestClient, admin_user_token: dict):
    derived = _create_dataset(test_client, admin_user_token, "processed")
    resp = test_client.post(
        f"/v1/datasets/{derived}/derivations",
        headers=admin_user_token,
        json={},
    )
    assert resp.status_code == 422, resp.text


def test_derivation_requires_authorisation(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """Seed through the service layer so no auth override is installed, leaving
    the HTTP request genuinely anonymous."""
    dataset = DatasetService(session).create(
        DatasetCreate(name="processed", level=1), user=admin_user
    )
    session.commit()
    assert dataset.id is not None

    resp = test_client.post(
        f"/v1/datasets/{dataset.id}/derivations",
        json={"source_label": "anonymous claim"},
    )
    assert resp.status_code in (401, 403), resp.text
    assert DatasetService(session).get_derivations(dataset.id, admin_user) == []


def test_restricted_dataset_derivations_are_not_public(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    """Provenance must not be reachable by going straight to the sub-resource of a
    dataset whose own endpoint returns 403."""
    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Tokamak"), user=admin_user
    )
    secret = DatasetService(session).create(
        DatasetCreate(
            name="secret",
            level=0,
            device_name="MAST",
            access_level=AccessLevel.RESTRICTED,
        ),
        user=admin_user,
    )
    assert secret.id is not None
    DatasetService(session).add_derivation(
        dataset_id=secret.id,
        obj_in=DatasetDerivationCreate(source_label="confidential upstream"),
        user=admin_user,
    )
    session.commit()

    assert test_client.get(f"/v1/datasets/id/{secret.id}").status_code == 403
    resp = test_client.get(f"/v1/datasets/{secret.id}/derivations")
    assert resp.status_code == 403, resp.text


def test_jsonld_exposes_derivation(test_client: TestClient, admin_user_token: dict):
    upstream = _create_dataset(test_client, admin_user_token, "raw")
    derived = _create_dataset(
        test_client,
        admin_user_token,
        "processed",
        derived_from=[{"source_dataset_id": upstream}],
    )

    resp = test_client.get(
        f"/v1/datasets/id/{derived}",
        headers={**admin_user_token, "Accept": "application/ld+json"},
    )
    assert resp.status_code == 200
    sources = resp.json()["prov:wasDerivedFrom"]
    assert sources[0]["@id"].endswith(f"/datasets/{upstream}")


def test_lineage_endpoint_nests_the_chain(
    test_client: TestClient, admin_user_token: dict
):
    raw = _create_dataset(test_client, admin_user_token, "raw")
    calibrated = _create_dataset(
        test_client,
        admin_user_token,
        "calibrated",
        derived_from=[{"source_dataset_id": raw}],
    )
    profile = _create_dataset(
        test_client,
        admin_user_token,
        "profile",
        derived_from=[
            {"source_dataset_id": calibrated},
            {"source_identifier": "10.5281/zenodo.123", "source_label": "On Zenodo"},
        ],
    )

    resp = test_client.get(f"/v1/datasets/{profile}/lineage")
    assert resp.status_code == 200
    body = resp.json()

    assert body["dataset_id"] == profile
    upstream, external = body["derived_from"]
    assert upstream["name"] == "calibrated"
    assert upstream["derived_from"][0]["name"] == "raw"
    assert upstream["derived_from"][0]["derived_from"] == []
    assert external["identifier"] == "10.5281/zenodo.123"

    # exclude_none keeps the flags off every node that did not stop early
    assert "seen" not in upstream
    assert "restricted" not in upstream
    assert "missing" not in upstream


def test_lineage_endpoint_404s_for_an_unknown_dataset(test_client: TestClient):
    assert test_client.get("/v1/datasets/9999/lineage").status_code == 404


def test_deleting_an_asserted_upstream_returns_409(
    test_client: TestClient, admin_user_token: dict
):
    """The refusal reaches the caller as a conflict, naming what depends on it."""
    raw = _create_dataset(test_client, admin_user_token, "raw")
    derived = _create_dataset(
        test_client,
        admin_user_token,
        "calibrated",
        derived_from=[{"source_dataset_id": raw}],
    )

    resp = test_client.delete(f"/v1/datasets/{raw}", headers=admin_user_token)

    assert resp.status_code == 409
    assert str(derived) in resp.json()["detail"]
    assert test_client.get(f"/v1/datasets/id/{raw}").status_code == 200
