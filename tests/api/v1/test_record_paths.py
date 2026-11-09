import pytest
from fastapi.testclient import TestClient

CREATE = {
    "datasets": ("/v1/datasets", {"level": 1, "url": "url"}),
    "collections": ("/v1/collections", {}),
    "sources": ("/v1/sources/", {"kind": "software"}),
}


@pytest.mark.parametrize("kind", CREATE)
def test_get_patch_and_delete_on_one_path_address_one_record(
    test_client: TestClient, admin_user_token: dict, kind: str
):
    """A global record named after another record's id is never the one addressed."""
    create_path, body = CREATE[kind]

    def create(name: str) -> int:
        response = test_client.post(
            create_path, headers=admin_user_token, json={"name": name, **body}
        )
        assert response.status_code == 201
        return response.json()["id"]

    target = create("target")
    decoy = create(str(target))
    path = f"/v1/{kind}/{target}"

    assert test_client.get(path, headers=admin_user_token).json()["id"] == target
    patched = test_client.patch(
        path, headers=admin_user_token, json={"name": "renamed"}
    )
    assert patched.json()["id"] == target
    assert test_client.get(path, headers=admin_user_token).json()["name"] == "renamed"
    assert test_client.delete(path, headers=admin_user_token).status_code == 204
    assert test_client.get(path, headers=admin_user_token).status_code == 404

    survivor = test_client.get(f"/v1/{kind}/{decoy}", headers=admin_user_token)
    assert survivor.json()["name"] == str(target)
