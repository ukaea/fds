from fastapi.testclient import TestClient


def test_create_source_admin(test_client: TestClient, admin_user_token: dict):
    response = test_client.post(
        "/v1/sources/",
        headers=admin_user_token,
        json={
            "name": "API Source",
            "description": "Created via API",
            "kind": "software",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "API Source"
    assert "id" in data


def test_create_source_non_admin(test_client: TestClient, non_admin_user_token: dict):
    response = test_client.post(
        "/v1/sources/",
        headers=non_admin_user_token,
        json={"name": "Non Admin Source", "kind": "software"},
    )
    assert response.status_code == 403


def test_create_source_unauthorized(test_client: TestClient):
    response = test_client.post(
        "/v1/sources/",
        json={"name": "Unauthorized Source", "kind": "software"},
    )
    assert response.status_code == 403


def test_read_sources(test_client: TestClient, admin_user_token: dict):
    test_client.post(
        "/v1/sources/",
        headers=admin_user_token,
        json={"name": "Source A", "kind": "software"},
    )
    test_client.post(
        "/v1/sources/",
        headers=admin_user_token,
        json={"name": "Source B", "kind": "software"},
    )

    response = test_client.get("/v1/sources/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_find_source_by_name(test_client: TestClient, admin_user_token: dict):
    for name in ("LookupName", "OtherName"):
        test_client.post(
            "/v1/sources/",
            headers=admin_user_token,
            json={"name": name, "kind": "software"},
        )

    response = test_client.get("/v1/sources/?name=LookupName")
    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["LookupName"]


def test_find_source_by_absent_name(test_client: TestClient):
    response = test_client.get("/v1/sources/?name=NonExistent")
    assert response.status_code == 200
    assert response.json() == []


def test_read_source_not_found(test_client: TestClient):
    response = test_client.get("/v1/sources/999999")
    assert response.status_code == 404
