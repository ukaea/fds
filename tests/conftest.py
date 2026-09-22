import io
import json
import logging
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from alembic import command
from app.auth.security import (
    AuthenticatedUser,
    get_token_claims,
)
from app.core.config import TrustedIdP, config
from app.core.db import _json_serializer, get_session
from app.core.logging import setup_logging
from app.main import app


@pytest.fixture(scope="session")
def database_url() -> Generator[str, None, None]:
    """A PostgreSQL database for the test run.

    FDS_TEST_DB_URL points at one you are already running, which is what CI and
    anyone with the compose stack up will use. Otherwise a container is started
    for the session and thrown away afterwards.
    """
    supplied = os.environ.get("FDS_TEST_DB_URL")
    if supplied:
        yield supplied
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - depends on the environment
        pytest.skip(
            "no test database: set FDS_TEST_DB_URL, or install the dev "
            "dependencies so a container can be started"
        )

    with PostgresContainer("postgres:17", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def engine(database_url: str):
    """One engine per run, with the schema built by the committed migrations.

    Building it with Alembic rather than `create_all` means every run also
    proves the migrations produce the schema the models expect.
    """
    alembic_config = AlembicConfig(str(Path(__file__).parent.parent / "alembic.ini"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url, json_serializer=_json_serializer)
    yield engine
    engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine) -> Generator[Session, None, None]:
    """A session whose writes are discarded when the test ends.

    Each test runs inside a transaction that is rolled back, so the database is
    built once for the run rather than once per test. `create_savepoint` means
    the service layer's own commits release a savepoint instead of committing,
    so nothing escapes into the next test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(name="test_client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_session, None)


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
    app.dependency_overrides.pop(get_token_claims, None)


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
    app.dependency_overrides.pop(get_token_claims, None)


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
    app.dependency_overrides.pop(get_token_claims, None)


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
    app.dependency_overrides.pop(get_token_claims, None)


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


@pytest.fixture
def log_lines(monkeypatch):
    """Capture the process's real log output, as parsed JSON lines."""
    monkeypatch.setattr(config, "LOG_FORMAT", "json")
    setup_logging()

    stream = io.StringIO()
    for name in ("", "uvicorn", "uvicorn.error"):
        for handler in logging.getLogger(name).handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(stream)

    def read() -> list[dict]:
        written = stream.getvalue()
        stream.seek(0)
        stream.truncate()
        return [
            json.loads(line) for line in written.splitlines() if line.startswith("{")
        ]

    yield read

    monkeypatch.undo()
    setup_logging()
