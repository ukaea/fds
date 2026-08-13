import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.device import DeviceCreate
from app.models.source import SourceCreate, SourceKind
from app.services.device_service import DeviceService
from app.services.source_service import SourceService


@pytest.fixture(name="setup_devices")
def setup_devices_fixture(
    session: Session,
    admin_user: AuthenticatedUser,
):
    device_service = DeviceService(session)
    dev1 = device_service.create(
        DeviceCreate(name="DeviceA", type="Tokamak"), user=admin_user
    )
    dev2 = device_service.create(
        DeviceCreate(name="DeviceB", type="Stellarator"), user=admin_user
    )
    return dev1, dev2


def test_create_source_nested_endpoint(
    test_client: TestClient,
    setup_devices,
    admin_user_token: dict[str, str],
):
    dev1, dev2 = setup_devices

    # 1. Create Source via nested endpoint
    source_data = {
        "name": "source_on_device_a",
        "description": "Nested creation test",
        "kind": "software",
        # device_name is NOT in body, should be inferred from URL
    }

    resp = test_client.post(
        f"/api/v1/devices/{dev1.name}/sources",
        json=source_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "source_on_device_a"
    assert data["device_name"] == dev1.name


def test_list_sources_nested_endpoint(
    test_client: TestClient,
    session: Session,
    setup_devices,
    admin_user_token: dict[str, str],
    admin_user: AuthenticatedUser,
):
    dev1, dev2 = setup_devices
    source_service = SourceService(session)

    # Create sources on DeviceA
    source_service.create(
        SourceCreate(name="s1_devA", device_name=dev1.name, kind=SourceKind.SOFTWARE),
        user=admin_user,
    )
    source_service.create(
        SourceCreate(name="s2_devA", device_name=dev1.name, kind=SourceKind.SOFTWARE),
        user=admin_user,
    )

    # Create source on DeviceB
    source_service.create(
        SourceCreate(name="s3_devB", device_name=dev2.name, kind=SourceKind.SOFTWARE),
        user=admin_user,
    )

    # Create global source
    source_service.create(
        SourceCreate(name="s4_global", kind=SourceKind.SOFTWARE), user=admin_user
    )

    # 1. List sources for DeviceA
    resp = test_client.get(
        f"/api/v1/devices/{dev1.name}/sources",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    names = {s["name"] for s in data}
    assert "s1_devA" in names
    assert "s2_devA" in names
    assert "s3_devB" not in names
    assert "s4_global" not in names

    # 2. List sources for DeviceB
    resp = test_client.get(
        f"/api/v1/devices/{dev2.name}/sources",
        headers=admin_user_token,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "s3_devB"


def test_create_source_nested_invalid_device(
    test_client: TestClient,
    admin_user_token: dict[str, str],
):
    source_data = {"name": "source_invalid", "kind": "software"}
    resp = test_client.post(
        "/api/v1/devices/non_existent_device/sources",
        json=source_data,
        headers=admin_user_token,
    )
    assert resp.status_code == 404
