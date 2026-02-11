from fastapi.testclient import TestClient


def test_create_source_admin(test_client: TestClient, admin_user_token: dict):
    response = test_client.post(
        "/api/v1/sources/",
        headers=admin_user_token,
        json={"name": "API Source", "description": "Created via API"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "API Source"
    assert "id" in data


def test_create_source_non_admin(test_client: TestClient, non_admin_user_token: dict):
    response = test_client.post(
        "/api/v1/sources/",
        headers=non_admin_user_token,
        json={"name": "Non Admin Source"},
    )
    assert response.status_code == 403


def test_create_source_unauthorized(test_client: TestClient):
    response = test_client.post(
        "/api/v1/sources/",
        json={"name": "Unauthorized Source"},
    )
    assert response.status_code == 403


def test_read_sources(test_client: TestClient, admin_user_token: dict):
    test_client.post(
        "/api/v1/sources/",
        headers=admin_user_token,
        json={"name": "Source A"},
    )
    test_client.post(
        "/api/v1/sources/",
        headers=admin_user_token,
        json={"name": "Source B"},
    )

    response = test_client.get("/api/v1/sources/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_read_source_by_name(test_client: TestClient, admin_user_token: dict):
    test_client.post(
        "/api/v1/sources/",
        headers=admin_user_token,
        json={"name": "LookupName"},
    )

    response = test_client.get("/api/v1/sources/LookupName")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "LookupName"


def test_read_source_not_found(test_client: TestClient):
    response = test_client.get("/api/v1/sources/NonExistent")
    assert response.status_code == 404
