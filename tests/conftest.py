from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from app.auth.security import (
    AuthenticatedUser,
    get_token_claims,
)
from app.core.config import TrustedIdP, config
from app.core.db import _json_serializer, get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        json_serializer=_json_serializer,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="test_client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="admin_user")
def admin_user_fixture() -> AuthenticatedUser:
    return AuthenticatedUser(id="admin", scopes=("fds-admin",))


@pytest.fixture(name="mast_admin_user")
def mast_admin_user_fixture() -> AuthenticatedUser:
    return AuthenticatedUser(id="mast-admin", scopes=("mast_admin",))


@pytest.fixture
def admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override the get_token_claims dependency to return claims
    for an admin user.
    """
    claims = {
        "sub": "test-admin-user",
        "scp": "fds-admin",
        "iss": "https://test-idp.com",
    }
    app.dependency_overrides[get_token_claims] = lambda: claims
    yield {"Authorization": "Bearer fake-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def non_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override the get_token_claims dependency to return claims
    for a non-admin user.
    """
    claims = {
        "sub": "test-non-admin-user",
        "scp": "some-other-scope",
        "iss": "https://test-idp.com",
    }
    app.dependency_overrides[get_token_claims] = lambda: claims
    yield {"Authorization": "Bearer fake-non-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def mast_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override get_token_claims to return claims for a mast_admin user.
    """
    claims = {
        "sub": "test-mast-admin-user",
        "scp": "mast_admin",
        "iss": "https://test-idp.com",
    }
    app.dependency_overrides[get_token_claims] = lambda: claims
    yield {"Authorization": "Bearer fake-mast-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def jet_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override get_token_claims to return claims for a jet_admin user.
    """
    claims = {
        "sub": "test-jet-admin-user",
        "scp": "jet_admin",
        "iss": "https://test-idp.com",
    }
    app.dependency_overrides[get_token_claims] = lambda: claims
    yield {"Authorization": "Bearer fake-jet-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    monkeypatch.setattr(config, "OIDC_AUDIENCE", "test-audience")

    # Initialize TRUSTED_IDPS with a default test IdP that allows all scopes
    # This ensures existing tests (which don't care about IdP) pass by default.
    default_test_idp = TrustedIdP(issuer="https://test-idp.com", allowed_scopes=["*"])
    monkeypatch.setattr(config, "TRUSTED_IDPS", [default_test_idp])


@pytest.fixture
def idp_config(monkeypatch):
    """Configure TRUSTED_IDPS with a single named issuer for policy tests."""
    monkeypatch.setattr(
        config,
        "TRUSTED_IDPS",
        [TrustedIdP(issuer="https://idp-a.example.com", allowed_scopes=["*"])],
    )


@pytest.fixture
def two_idp_config(monkeypatch):
    """Configure TRUSTED_IDPS with two named issuers for policy tests."""
    monkeypatch.setattr(
        config,
        "TRUSTED_IDPS",
        [
            TrustedIdP(issuer="https://idp-a.example.com", allowed_scopes=["*"]),
            TrustedIdP(issuer="https://idp-b.example.com", allowed_scopes=["*"]),
        ],
    )


@pytest.fixture
def mock_jwks_client(mocker):
    """Global mock for JWKS Client"""
    client = mocker.AsyncMock()
    client.get_signing_key.return_value = "mock_public_key"
    return client


@pytest.fixture
def mock_jwt_decode(mocker):
    """Global mock for jwt.decode"""
    return mocker.patch("app.auth.security.jwt.decode")


@pytest.fixture
def mock_s3_provider(mocker):
    # Mock the get_provider_for_protocol to return a mock S3 provider
    mock_prov = mocker.Mock()
    # Providers return a mapping payload; use an empty mapping by default.
    mock_prov.generate_credentials.return_value = {}
    # When initialized, S3CredentialProvider will be used, but we want to intercept the factory
    mocker.patch(
        "app.services.file_access_service.get_provider_for_endpoint",
        return_value=mock_prov,
    )
    return mock_prov


@pytest.fixture
def mock_check_shot_operator(mocker):
    return mocker.patch("app.services.file_access_service.check_shot_operator")
