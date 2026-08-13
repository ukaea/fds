import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


@pytest.fixture(name="setup_device")
def setup_device_fixture(
    session: Session,
    admin_user: AuthenticatedUser,
):
    device_service = DeviceService(session)
    return device_service.create(
        DeviceCreate(name="SourceDevice", type="Tokamak"), user=admin_user
    )


def test_create_source_with_device(
    test_client: TestClient,
    setup_device,
    admin_user_token: dict[str, str],
):
    device = setup_device

    # 1. Create Source with Device
    source_data = {
        "name": "device_specific_source",
        "description": "Source on a device",
        "device_name": device.name,
        "kind": "software",
    }

    resp = test_client.post(
        "/api/v1/sources/",
        json=source_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "device_specific_source"
    assert data["device_name"] == device.name


def test_create_source_invalid_device(
    test_client: TestClient,
    admin_user_token: dict[str, str],
):
    source_data = {
        "name": "invalid_device_source",
        "device_name": "non_existent_device",
        "kind": "software",
    }

    resp = test_client.post(
        "/api/v1/sources/",
        json=source_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 404
