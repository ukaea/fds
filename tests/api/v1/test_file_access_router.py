from fastapi.testclient import TestClient


def test_get_credentials(test_client: TestClient, admin_user_token: dict):
    """
    Test the file-access credentials endpoint.
    Should return a CredentialManifest with 'tokens' and 'resource_map'.
    """
    response = test_client.post(
        "/api/v1/file-access/credentials",
        headers=admin_user_token,
        json={"shot_id": None},  # Empty filter
    )
    assert response.status_code == 200
    data = response.json()

    assert "resource_map" in data
    # We might expect empty resource_map if DB is empty, but status 200 confirms wiring.


def test_get_credentials_unauthorized(test_client: TestClient):
    """
    Anonymous users should also be allowed (returning empty manifest if they can't see anything,
    or public data tokens if available).
    Wait, FileAccessService logic requires 'check_download_permission'.
    Public datasets ARE allowed for anonymous.
    So status should be 200, not 401/403 (unless we enforced strict auth on the endpoint).
    Let's check the router definition. It uses 'user: CurrentUserDep'.
    CurrentUserDep allows anonymous.
    """
    response = test_client.post("/api/v1/file-access/credentials", json={})
    assert response.status_code == 200
    data = response.json()
    assert "resource_map" in data
