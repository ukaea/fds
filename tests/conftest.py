import importlib
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.main import app
from app.core.db import get_session

# Dynamically import all models to ensure they are registered with SQLModel.metadata
models_dir = Path.cwd() / "app" / "models"
for f in models_dir.glob("*.py"):
    module_name = f.stem
    importlib.import_module(f"app.models.{module_name}")
target_metadata = SQLModel.metadata


@pytest.fixture(name="engine")
def engine_fixture() -> Generator:
    test_engine = create_engine(
        "sqlite:///:memory:", echo=False, connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(test_engine)

    yield test_engine

    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session) -> Generator[TestClient, None, None]:
    def get_session_override() -> Session:
        return session

    app.dependency_overrides[get_session] = get_session_override

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
