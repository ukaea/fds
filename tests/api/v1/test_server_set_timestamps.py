import pytest
from fastapi.testclient import TestClient

BACKDATED = "2001-01-01T00:00:00Z"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/devices/", {"name": "listed"}),
        ("/v1/devices/listed/shots/", {"id": "1"}),
        ("/v1/devices/listed/datasets", {"name": "raw"}),
        ("/v1/devices/listed/collections", {"name": "bundle"}),
    ],
)
def test_a_caller_cannot_set_when_fds_listed_a_record(
    test_client: TestClient, admin_user_token: dict, path: str, body: dict
):
    if path != "/v1/devices/":
        test_client.post(
            "/v1/devices/", headers=admin_user_token, json={"name": "listed"}
        )

    response = test_client.post(
        path,
        headers=admin_user_token,
        json={**body, "created_at": BACKDATED, "updated_at": BACKDATED},
    )

    assert response.status_code == 201, response.text
    assert not response.json()["created_at"].startswith("2001")
    assert not response.json()["updated_at"].startswith("2001")
