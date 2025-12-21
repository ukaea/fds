from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from app.auth.security import get_token_claims
from app.core.db import get_session
from app.main import app

from app.models import dataset, datasetsource, device, shot, source  # noqa: F401


@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override the get_token_claims dependency to return claims
    for an admin user.
    """
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "test-admin-user",
        "scp": "fds-admin",
    }
    yield {"Authorization": "Bearer fake-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def non_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override the get_token_claims dependency to return claims
    for a non-admin user.
    """
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "test-non-admin-user",
        "scp": "some-other-scope",
    }
    yield {"Authorization": "Bearer fake-non-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def mast_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override get_token_claims to return claims for a mast_admin user.
    """
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "test-mast-admin-user",
        "scp": "mast_admin",
    }
    yield {"Authorization": "Bearer fake-mast-admin-token"}
    app.dependency_overrides.clear()


@pytest.fixture
def jet_admin_user_token() -> Generator[dict[str, str], None, None]:
    """
    Fixture to override get_token_claims to return claims for a jet_admin user.
    """
    app.dependency_overrides[get_token_claims] = lambda: {
        "sub": "test-jet-admin-user",
        "scp": "jet_admin",
    }
    yield {"Authorization": "Bearer fake-jet-admin-token"}
    app.dependency_overrides.clear()



@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    from app.core.config import config
    monkeypatch.setattr(config, "OIDC_DOMAIN", "test-domain.com")
    monkeypatch.setattr(config, "OIDC_AUDIENCE", "test-audience")
