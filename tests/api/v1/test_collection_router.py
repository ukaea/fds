from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.collection import CollectionCreate
from app.models.dataset import DatasetCreate
from app.models.device import DeviceCreate
from app.models.file_access import S3Credentials
from app.models.shot import ShotCreate
from app.services.collection_service import CollectionService
from app.services.dataset_service import DatasetService
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService

admin_user = AuthenticatedUser(id="admin", scopes=("fds-admin",))


def _make_device(session: Session, name="DEV"):
    DeviceService(session).create(
        DeviceCreate(name=name, type="Tokamak"), user=admin_user
    )


def _make_shot(session: Session, shot_id="s1", device="DEV"):
    ShotService(session).create(
        ShotCreate(id=shot_id, device_name=device), user=admin_user
    )


def _make_dataset(
    session: Session, name: str = "ds", device: str = "DEV", shot_id: str | None = None
) -> int:
    ds = DatasetService(session).create(
        DatasetCreate(
            name=name,
            level=1,
            url=f"s3://bucket/{name}",
            device_name=device,
            shot_id=shot_id,
        ),
        user=admin_user,
    )
    assert ds.id is not None
    return ds.id


def _make_collection(
    session: Session, name: str, device: str | None = None, shot_id: str | None = None
) -> int:
    col = CollectionService(session).create(
        CollectionCreate(name=name, device_name=device, shot_id=shot_id),
        user=admin_user,
    )
    assert col.id is not None
    return col.id


def test_create_global_collection(test_client: TestClient, admin_user_token: dict):
    """POST /collections creates a global Collection and returns 201."""
    response = test_client.post(
        "/api/v1/collections",
        headers=admin_user_token,
        json={"name": "jintrac-42", "title": "JINTRAC Run 42"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "jintrac-42"
    assert data["title"] == "JINTRAC Run 42"
    assert "device_name" not in data
    assert "shot_id" not in data


def test_create_global_collection_unauthorized(
    test_client: TestClient, non_admin_user_token: dict
):
    """Non-admin users cannot create global Collections."""
    response = test_client.post(
        "/api/v1/collections",
        headers=non_admin_user_token,
        json={"name": "forbidden"},
    )
    assert response.status_code == 403


def test_read_global_collections(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /collections returns all accessible global Collections."""
    _make_collection(session, "run-a")
    _make_collection(session, "run-b")

    response = test_client.get("/api/v1/collections", headers=admin_user_token)
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "run-a" in names
    assert "run-b" in names


def test_read_global_collection_by_name(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /collections/{name} retrieves a specific global Collection."""
    _make_collection(session, "named-run")

    response = test_client.get(
        "/api/v1/collections/named-run", headers=admin_user_token
    )
    assert response.status_code == 200
    assert response.json()["name"] == "named-run"


def test_read_global_collection_by_name_not_found(
    test_client: TestClient, admin_user_token: dict
):
    """GET /collections/{name} returns 404 for an absent Collection."""
    response = test_client.get("/api/v1/collections/ghost", headers=admin_user_token)
    assert response.status_code == 404


def test_create_device_collection(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """POST /devices/{device}/collections creates a device-level Collection."""
    _make_device(session)

    response = test_client.post(
        "/api/v1/devices/DEV/collections",
        headers=admin_user_token,
        json={"name": "machine-diags"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "machine-diags"
    assert data["device_name"] == "dev"
    assert "shot_id" not in data


def test_read_device_collections(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /devices/{device}/collections returns only device-level Collections."""
    _make_device(session)
    _make_collection(session, "d-col-1", device="DEV")
    _make_collection(session, "global-col")

    response = test_client.get(
        "/api/v1/devices/DEV/collections", headers=admin_user_token
    )
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "d-col-1" in names
    assert "global-col" not in names


def test_read_device_collection_by_name(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /devices/{device}/collections/{name} retrieves by name."""
    _make_device(session)
    _make_collection(session, "cfg", device="DEV")

    response = test_client.get(
        "/api/v1/devices/DEV/collections/cfg", headers=admin_user_token
    )
    assert response.status_code == 200
    assert response.json()["name"] == "cfg"


def test_create_shot_collection(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """POST /devices/{device}/shots/{shot}/collections creates a shot-scoped Collection."""
    _make_device(session)
    _make_shot(session)

    response = test_client.post(
        "/api/v1/devices/DEV/shots/s1/collections",
        headers=admin_user_token,
        json={"name": "jintrac-outputs", "title": "JINTRAC outputs"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "jintrac-outputs"
    assert data["device_name"] == "dev"
    assert data["shot_id"] == "s1"


def test_read_shot_collections(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /devices/{device}/shots/{shot}/collections filters by shot."""
    _make_device(session)
    _make_shot(session, "s1")
    _make_shot(session, "s2")
    _make_collection(session, "col-s1", device="DEV", shot_id="s1")
    _make_collection(session, "col-s2", device="DEV", shot_id="s2")

    response = test_client.get(
        "/api/v1/devices/DEV/shots/s1/collections", headers=admin_user_token
    )
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert "col-s1" in names
    assert "col-s2" not in names


def test_read_shot_collection_by_name(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /devices/{device}/shots/{shot}/collections/{name} retrieves by name."""
    _make_device(session)
    _make_shot(session)
    _make_collection(session, "run-out", device="DEV", shot_id="s1")

    response = test_client.get(
        "/api/v1/devices/DEV/shots/s1/collections/run-out", headers=admin_user_token
    )
    assert response.status_code == 200
    assert response.json()["name"] == "run-out"


def test_update_collection(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """PATCH /collections/{id} applies a partial update."""
    col_id = _make_collection(session, "before")

    response = test_client.patch(
        f"/api/v1/collections/{col_id}",
        headers=admin_user_token,
        json={"title": "After"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "After"


def test_delete_collection(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """DELETE /collections/{id} removes the Collection and returns 204."""
    col_id = _make_collection(session, "to-delete")

    response = test_client.delete(
        f"/api/v1/collections/{col_id}", headers=admin_user_token
    )
    assert response.status_code == 204

    # Confirm it is gone
    get_response = test_client.get(
        "/api/v1/collections/to-delete", headers=admin_user_token
    )
    assert get_response.status_code == 404


def test_add_and_remove_dataset_membership(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """POST /collections/{id}/datasets/{ds_id} adds a member; DELETE removes it."""
    _make_device(session)
    _make_shot(session)
    ds_id = _make_dataset(session, name="profiles", device="DEV", shot_id="s1")
    col_id = _make_collection(session, "run")

    # Add
    add_resp = test_client.post(
        f"/api/v1/collections/{col_id}/datasets/{ds_id}",
        headers=admin_user_token,
    )
    assert add_resp.status_code == 204

    # Verify inlined in GET response
    get_resp = test_client.get("/api/v1/collections/run", headers=admin_user_token)
    dataset_ids = [d["id"] for d in get_resp.json().get("datasets", [])]
    assert ds_id in dataset_ids

    # Remove
    del_resp = test_client.delete(
        f"/api/v1/collections/{col_id}/datasets/{ds_id}",
        headers=admin_user_token,
    )
    assert del_resp.status_code == 204

    # Confirm removed
    get_after = test_client.get("/api/v1/collections/run", headers=admin_user_token)
    assert get_after.json().get("datasets") is None


def test_add_dataset_duplicate_returns_409(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """Adding the same Dataset twice returns 409 Conflict."""
    _make_device(session)
    ds_id = _make_dataset(session, device="DEV")
    col_id = _make_collection(session, "run")

    test_client.post(
        f"/api/v1/collections/{col_id}/datasets/{ds_id}", headers=admin_user_token
    )
    response = test_client.post(
        f"/api/v1/collections/{col_id}/datasets/{ds_id}", headers=admin_user_token
    )
    assert response.status_code == 409


def test_add_and_remove_child_collection(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """POST /collections/{parent}/collections/{child} nests a child; DELETE unlinks it."""
    parent_id = _make_collection(session, "parent")
    child_id = _make_collection(session, "child")

    add_resp = test_client.post(
        f"/api/v1/collections/{parent_id}/collections/{child_id}",
        headers=admin_user_token,
    )
    assert add_resp.status_code == 204

    # Verify child appears in parent's read model
    get_resp = test_client.get("/api/v1/collections/parent", headers=admin_user_token)
    child_ids = [c["id"] for c in get_resp.json().get("child_collections", [])]
    assert child_id in child_ids

    # Remove
    del_resp = test_client.delete(
        f"/api/v1/collections/{parent_id}/collections/{child_id}",
        headers=admin_user_token,
    )
    assert del_resp.status_code == 204

    get_after = test_client.get("/api/v1/collections/parent", headers=admin_user_token)
    assert get_after.json().get("child_collections") is None


def test_add_child_collection_self_reference_returns_422(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """Nesting a Collection inside itself returns 422."""
    col_id = _make_collection(session, "self")

    response = test_client.post(
        f"/api/v1/collections/{col_id}/collections/{col_id}",
        headers=admin_user_token,
    )
    assert response.status_code == 422


def test_collection_jsonld_response(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /collections/{name} with Accept: application/ld+json returns dcat:Catalog."""
    _make_collection(session, "ld-col")

    response = test_client.get(
        "/api/v1/collections/ld-col",
        headers={**admin_user_token, "accept": "application/ld+json"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")
    data = response.json()
    assert data["@type"] == "dcat:Catalog"
    # No root_url set → no dcat:distribution node
    assert "dcat:distribution" not in data


def test_collection_jsonld_includes_root_url_distribution(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """When a Collection has ``root_url``, JSON-LD includes a dcat:distribution
    node with dcat:accessURL pointing at the store root (per ADR-0029)."""
    CollectionService(session).create(
        CollectionCreate(
            name="ld-col-root",
            root_url="s3://fds-data/shots/50000/analysed",
        ),
        user=admin_user,
    )

    response = test_client.get(
        "/api/v1/collections/ld-col-root",
        headers={**admin_user_token, "accept": "application/ld+json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["dcat:distribution"] == {
        "@type": "dcat:Distribution",
        "dcat:accessURL": "s3://fds-data/shots/50000/analysed",
    }


def test_collection_activity_not_found_when_no_activity(
    test_client: TestClient, session: Session, admin_user_token: dict
):
    """GET /collections/{id}/activity returns 404 when no activity is linked."""
    col_id = _make_collection(session, "no-prov")

    response = test_client.get(
        f"/api/v1/collections/{col_id}/activity", headers=admin_user_token
    )
    assert response.status_code == 404


def test_collection_include_storage_options(
    test_client: TestClient, session: Session, admin_user_token: dict, mocker
):
    """include_storage_options=true enriches inline datasets on any Collection endpoint."""
    _make_device(session, "CRED")
    _make_shot(session, "s99", "CRED")
    ds_id = _make_dataset(session, "cred-ds", "CRED", "s99")
    col_id = _make_collection(session, "cred-col", "CRED", "s99")
    CollectionService(session).add_dataset(col_id, ds_id, user=admin_user)

    mock_provider = mocker.MagicMock()
    mock_provider.generate_credentials.return_value = {
        "bucket": S3Credentials(
            access_key_id="c_key",
            secret_access_key="c_sec",
            session_token="c_tok",
            expiration=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
        )
    }
    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=mock_provider,
    )

    # Without flag — datasets inlined but no credentials
    resp = test_client.get(
        "/api/v1/devices/CRED/shots/s99/collections/cred-col",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    assert resp.json()["datasets"][0].get("storage_options") is None

    # With flag — credentials present on every inlined dataset
    resp2 = test_client.get(
        "/api/v1/devices/CRED/shots/s99/collections/cred-col?include_storage_options=true",
        headers=admin_user_token,
    )
    assert resp2.status_code == 200
    ds = resp2.json()["datasets"][0]
    assert ds["storage_options"]["key"] == "c_key"
    assert ds["storage_options"]["secret"] == "c_sec"
