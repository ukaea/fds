from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from fds.auth.security import AuthenticatedUser
from fds.core.config import TrustedIdP, config
from fds.models.device import DeviceCreate
from fds.models.policy import AccessLevel
from fds.services.device_service import DeviceService

METADATA = "http://testserver/.well-known/oauth-protected-resource"


def test_the_document_names_the_login_services_and_the_scope(
    test_client: TestClient, monkeypatch
):
    monkeypatch.setattr(
        config,
        "TRUSTED_IDPS",
        [
            TrustedIdP(issuer="https://login.example.org/realms/fds"),
            TrustedIdP(issuer="urn:fds:local", jwks_file=Path("local.jwks.json")),
            TrustedIdP(issuer="https://partner.example.org"),
        ],
    )
    monkeypatch.setattr(config, "OIDC_SCOPE", "fds")

    response = test_client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "http://testserver",
        "authorization_servers": [
            "https://login.example.org/realms/fds",
            "https://partner.example.org",
        ],
        "scopes_supported": ["fds"],
        "bearer_methods_supported": ["header"],
    }


def test_without_a_scope_or_a_login_service_the_document_names_neither(
    test_client: TestClient, monkeypatch
):
    monkeypatch.setattr(
        config,
        "TRUSTED_IDPS",
        [TrustedIdP(issuer="urn:fds:local", jwks_file=Path("local.jwks.json"))],
    )
    monkeypatch.setattr(config, "OIDC_SCOPE", "")

    response = test_client.get("/.well-known/oauth-protected-resource")

    assert response.json() == {
        "resource": "http://testserver",
        "bearer_methods_supported": ["header"],
    }


def test_the_document_names_the_address_the_caller_used(test_client: TestClient):
    response = test_client.get(
        "https://api.fds.example.org/.well-known/oauth-protected-resource"
    )

    assert response.json()["resource"] == "https://api.fds.example.org"


def test_the_mcp_server_has_a_document_naming_its_own_address(
    test_client: TestClient,
):
    response = test_client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.json()["resource"] == "http://testserver/mcp"
    assert response.json()["authorization_servers"] == ["https://test-idp.com"]


def test_a_refusal_without_a_token_says_where_to_get_one(
    test_client: TestClient, session: Session, admin_user: AuthenticatedUser
):
    DeviceService(session).create(
        DeviceCreate(name="jet", type="Tokamak", access_level=AccessLevel.RESTRICTED),
        user=admin_user,
    )
    session.commit()

    response = test_client.get("/v1/devices/jet")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == (
        f'Bearer resource_metadata="{METADATA}"'
    )


def test_a_token_fds_cannot_read_is_refused_as_invalid(test_client: TestClient):
    response = test_client.get(
        "/v1/devices/", headers={"Authorization": "Bearer not-a-token"}
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == (
        f'Bearer error="invalid_token", resource_metadata="{METADATA}"'
    )


def test_a_signed_in_caller_without_the_role_is_told_their_scope_is_insufficient(
    test_client: TestClient,
    session: Session,
    admin_user: AuthenticatedUser,
    non_admin_user_token: dict,
):
    DeviceService(session).create(
        DeviceCreate(name="mast", type="Tokamak"), user=admin_user
    )
    session.commit()

    response = test_client.post(
        "/v1/devices/mast/shots/",
        json={"id": "30420", "access_level": "public"},
        headers=non_admin_user_token,
    )

    assert response.status_code == 403
    assert response.headers["WWW-Authenticate"] == (
        f'Bearer error="insufficient_scope", resource_metadata="{METADATA}"'
    )
