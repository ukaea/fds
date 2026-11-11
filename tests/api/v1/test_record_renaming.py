import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from fds.models.activity import Activity
from fds.models.device import Device
from fds.models.shot import Shot


@pytest.fixture
def rename_contexts(session: Session):
    session.add_all([Device(name="mast"), Device(name="jet")])
    session.commit()
    session.add_all(
        [Shot(id="1", device_name="mast"), Shot(id="2", device_name="mast")]
    )
    session.commit()


def _create(test_client, headers, kind, name, context="", **fields):
    response = test_client.post(
        f"/v1{context}/{kind}",
        headers=headers,
        json={"name": name, "title": "Original title", **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize("with_shot", [False, True])
@pytest.mark.parametrize("new_name", ["renamed", None])
def test_device_rename_is_refused(
    test_client: TestClient,
    session: Session,
    admin_user_token: dict[str, str],
    with_shot,
    new_name,
):
    session.add(Device(name="mast", title="Original title"))
    session.commit()
    if with_shot:
        session.add(Shot(id="1", device_name="mast"))
        session.commit()

    response = test_client.patch(
        "/v1/devices/mast",
        headers=admin_user_token,
        json={"name": new_name, "title": "Changed title"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Cannot rename a device"
    stored = test_client.get("/v1/devices/mast", headers=admin_user_token)
    assert stored.status_code == 200
    assert stored.json()["title"] == "Original title"
    if with_shot:
        assert (
            test_client.get(
                "/v1/devices/mast/shots/1", headers=admin_user_token
            ).status_code
            == 200
        )


def test_device_update_accepts_same_name_in_different_case(
    test_client: TestClient, admin_user_token: dict[str, str], rename_contexts
):
    response = test_client.patch(
        "/v1/devices/MAST",
        headers=admin_user_token,
        json={"name": "MAST", "title": "New display name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "mast"
    assert response.json()["title"] == "New display name"


@pytest.mark.parametrize("kind", ["datasets", "collections"])
@pytest.mark.parametrize("context", ["", "/devices/mast", "/devices/mast/shots/1"])
def test_rename_to_existing_name_is_refused(
    test_client, admin_user_token, rename_contexts, kind, context
):
    _create(test_client, admin_user_token, kind, "taken", context)
    record_id = _create(test_client, admin_user_token, kind, "original", context)

    response = test_client.patch(
        f"/v1/{kind}/{record_id}",
        headers=admin_user_token,
        json={"name": "taken", "title": "Changed title"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"{kind[:-1].capitalize()} 'taken' already exists in this context"
    )
    stored = test_client.get(f"/v1/{kind}/{record_id}", headers=admin_user_token)
    assert stored.status_code == 200
    assert stored.json()["name"] == "original"
    assert stored.json()["title"] == "Original title"


@pytest.mark.parametrize("kind", ["datasets", "collections"])
@pytest.mark.parametrize("context", ["", "/devices/mast", "/devices/mast/shots/1"])
@pytest.mark.parametrize("new_name", ["original", "unused"])
def test_rename_accepts_unchanged_or_unused_name(
    test_client, admin_user_token, rename_contexts, kind, context, new_name
):
    record_id = _create(test_client, admin_user_token, kind, "original", context)
    response = test_client.patch(
        f"/v1/{kind}/{record_id}",
        headers=admin_user_token,
        json={"name": new_name, "title": "Changed title"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == new_name
    assert response.json()["title"] == "Changed title"


@pytest.mark.parametrize("kind", ["datasets", "collections"])
@pytest.mark.parametrize(
    "other_context",
    ["", "/devices/mast", "/devices/jet", "/devices/mast/shots/2"],
)
def test_rename_can_reuse_name_from_another_context(
    test_client, admin_user_token, rename_contexts, kind, other_context
):
    _create(test_client, admin_user_token, kind, "taken", other_context)
    record_id = _create(
        test_client, admin_user_token, kind, "original", "/devices/mast/shots/1"
    )
    response = test_client.patch(
        f"/v1/{kind}/{record_id}",
        headers=admin_user_token,
        json={"name": "taken"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("same_origin", [False, True])
def test_dataset_rename_respects_origin(
    test_client, admin_user_token, rename_contexts, same_origin
):
    origin = "https://catalogue.example.org"
    _create(test_client, admin_user_token, "datasets", "taken", origin=origin)
    record_id = _create(
        test_client,
        admin_user_token,
        "datasets",
        "original",
        origin=origin if same_origin else None,
    )
    response = test_client.patch(
        f"/v1/datasets/{record_id}",
        headers=admin_user_token,
        json={"name": "taken"},
    )
    assert response.status_code == (409 if same_origin else 200)


@pytest.mark.parametrize("same_activity", [False, True])
@pytest.mark.parametrize("change_activity", [False, True])
def test_dataset_rename_respects_resulting_activity(
    test_client, session, admin_user_token, same_activity, change_activity
):
    first, second = Activity(), Activity()
    session.add_all([first, second])
    session.commit()
    _create(test_client, admin_user_token, "datasets", "taken", activity_id=first.id)
    target_activity = first.id if same_activity else second.id
    record_id = _create(
        test_client,
        admin_user_token,
        "datasets",
        "original",
        activity_id=None if change_activity else target_activity,
    )
    patch: dict[str, object] = {"name": "taken"}
    if change_activity:
        patch["activity_id"] = target_activity
    response = test_client.patch(
        f"/v1/datasets/{record_id}", headers=admin_user_token, json=patch
    )
    assert response.status_code == (409 if same_activity else 200)
