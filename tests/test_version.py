import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from app import __version__


def test_health_reports_version(test_client: TestClient):
    """The liveness probe identifies the running build, so a deployer can confirm
    what landed and a bug report can say what it was filed against."""
    body = test_client.get("/health").json()
    assert body == {"status": "ok", "version": __version__}


def test_version_matches_pyproject():
    """``app.__version__`` feeds the OpenAPI spec and ``pyproject.toml`` feeds the
    release tag. Nothing installs the project as a distribution, so the two are
    written out separately and this is what stops them drifting."""
    pyproject = tomllib.loads(
        (Path(__file__).parent.parent / "pyproject.toml").read_text()
    )
    assert pyproject["project"]["version"] == __version__
