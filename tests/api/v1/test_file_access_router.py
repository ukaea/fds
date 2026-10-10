from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.file_access import S3Credentials
from app.models.shot import ShotCreate
from app.services.device_service import DeviceService
from app.services.shot_service import ShotService


def test_get_credentials(test_client: TestClient, admin_user_token: dict):
    """
    Test the file-access credentials endpoint.
    Should return a CredentialManifest with 'tokens' and 'resource_map'.
    """
    response = test_client.post(
        "/v1/file-access/credentials",
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
    response = test_client.post("/v1/file-access/credentials", json={})
    assert response.status_code == 200
    data = response.json()
    assert "resource_map" in data


def test_credentials_include_storage_options(
    test_client: TestClient, session: Session, admin_user_token: dict, mocker
):
    """``include_storage_options=true`` adds opener-ready kwargs to each entry.

    The bulk path then matches the single-dataset path: what comes back under
    ``storage_options`` goes straight into ``xr.open_dataset``.
    """
    admin = AuthenticatedUser(id="admin", scopes=("fds-admin",))
    DeviceService(session).create(DeviceCreate(name="BULK", type="Tokamak"), user=admin)
    ShotService(session).create(ShotCreate(id="7", device_name="BULK"), user=admin)
    session.commit()

    test_client.post(
        "/v1/devices/BULK/shots/7/datasets/",
        headers=admin_user_token,
        json={
            "name": "bulk1",
            "level": 1,
            "url": "s3://bulk/7/bulk1",
            "endpoint_url": "https://s3.example.org",
        },
    )

    mock_provider = mocker.MagicMock()
    mock_provider.generate_credentials.return_value = {
        "s3://bulk/7/bulk1": S3Credentials(
            access_key_id="b_key",
            secret_access_key="b_sec",
            session_token="b_tok",
            expiration=datetime.fromisoformat("2099-01-01T00:00:00+00:00"),
            endpoint_url="https://s3.example.org",
        )
    }
    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=mock_provider,
    )

    body = {"device_name": "BULK", "shot_id": "7"}

    plain = test_client.post(
        "/v1/file-access/credentials", headers=admin_user_token, json=body
    )
    assert plain.status_code == 200
    entry = plain.json()["resource_map"]["s3://bulk/7/bulk1"]
    assert entry["access_key_id"] == "b_key"
    assert entry.get("storage_options") is None

    enriched = test_client.post(
        "/v1/file-access/credentials?include_storage_options=true",
        headers=admin_user_token,
        json=body,
    )
    assert enriched.status_code == 200
    entry = enriched.json()["resource_map"]["s3://bulk/7/bulk1"]
    assert entry["access_key_id"] == "b_key"
    assert entry["storage_options"] == {
        "key": "b_key",
        "secret": "b_sec",
        "token": "b_tok",
        "client_kwargs": {"endpoint_url": "https://s3.example.org"},
    }
