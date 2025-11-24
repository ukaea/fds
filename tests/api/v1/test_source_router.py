from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.source import SourceCreate
from app.services.source_service import SourceService


def test_create_source(client: TestClient):
    response = client.post(
        "/api/v1/sources/",
        json={
            "name": "Thomson Scattering",
            "description": "Measures Te and ne profiles.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Thomson Scattering"
    assert data["description"] == "Measures Te and ne profiles."
    assert "id" in data


def test_read_sources(client: TestClient, session: Session):
    source_service = SourceService(session)
    source_service.create(SourceCreate(name="Source 1", description="Desc 1"))
    source_service.create(SourceCreate(name="Source 2", description="Desc 2"))

    response = client.get("/api/v1/sources/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Source 1"
    assert data[1]["name"] == "Source 2"


def test_read_source(client: TestClient, session: Session):
    source_service = SourceService(session)
    source = source_service.create(
        SourceCreate(name="ECE", description="Electron Cyclotron Emission")
    )

    response = client.get(f"/api/v1/sources/{source.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "ECE"
    assert data["id"] == source.id


def test_read_source_not_found(client: TestClient):
    response = client.get("/api/v1/sources/999")
    assert response.status_code == 404


def test_update_source(client: TestClient, session: Session):
    source_service = SourceService(session)
    source = source_service.create(
        SourceCreate(name="Initial Source", description="Initial Desc")
    )

    response = client.put(
        f"/api/v1/sources/{source.id}",
        json={"name": "Updated Source", "description": "Updated Desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Source"
    assert data["description"] == "Updated Desc"
    assert data["id"] == source.id


def test_delete_source(client: TestClient, session: Session):
    source_service = SourceService(session)
    source = source_service.create(
        SourceCreate(name="ToDelete", description="Delete this")
    )

    response = client.delete(f"/api/v1/sources/{source.id}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    response = client.get(f"/api/v1/sources/{source.id}")
    assert response.status_code == 404


def test_delete_source_not_found(client: TestClient):
    response = client.delete("/api/v1/sources/999")
    assert response.status_code == 404
