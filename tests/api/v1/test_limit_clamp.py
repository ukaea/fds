from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.core.config import config
from app.models.device import DeviceCreate
from app.services.device_service import DeviceService


def _seed_device(session: Session, admin_user: AuthenticatedUser, name: str = "MAST"):
    DeviceService(session).create(DeviceCreate(name=name, type="Tokamak"), admin_user)
    session.commit()


def test_limit_above_max_returns_422(test_client: TestClient):
    response = test_client.get(f"/api/v1/datasets?limit={config.MAX_LIMIT + 1}")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("less_than_equal" in str(item.get("type", "")) for item in detail)


def test_limit_zero_returns_422(test_client: TestClient):
    response = test_client.get("/api/v1/datasets?limit=0")
    assert response.status_code == 422


def test_limit_negative_returns_422(test_client: TestClient):
    response = test_client.get("/api/v1/datasets?limit=-5")
    assert response.status_code == 422


def test_limit_at_max_succeeds(test_client: TestClient):
    response = test_client.get(f"/api/v1/datasets?limit={config.MAX_LIMIT}")
    assert response.status_code == 200


def test_limit_default_succeeds(test_client: TestClient):
    response = test_client.get("/api/v1/datasets")
    assert response.status_code == 200


def test_shot_list_clamps_limit(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    _seed_device(session, admin_user)
    response = test_client.get(
        f"/api/v1/devices/MAST/shots?limit={config.MAX_LIMIT + 1}"
    )
    assert response.status_code == 422


def test_collection_list_clamps_limit(test_client: TestClient):
    response = test_client.get(f"/api/v1/collections?limit={config.MAX_LIMIT + 1}")
    assert response.status_code == 422


def test_device_list_clamps_limit(test_client: TestClient):
    response = test_client.get(f"/api/v1/devices/?limit={config.MAX_LIMIT + 1}")
    assert response.status_code == 422


def test_openapi_schema_documents_constraint(test_client: TestClient):
    """The generated OpenAPI schema reflects the bounded ``limit``
    constraint so client SDKs can validate ahead of the request."""
    spec = test_client.get("/openapi.json").json()
    params = spec["paths"]["/api/v1/datasets"]["get"]["parameters"]
    limit_param = next(p for p in params if p["name"] == "limit")
    assert limit_param["schema"]["maximum"] == config.MAX_LIMIT
    assert limit_param["schema"]["minimum"] == 1
