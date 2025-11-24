import pytest
from sqlmodel import Session
from sqlalchemy.exc import IntegrityError

from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.source_service import SourceService


def test_create_source(session: Session):
    service = SourceService(session)
    source_create = SourceCreate(
        name="Thomson Scattering", description="Measures Te and ne profiles."
    )
    source = service.create(source_create)

    assert source.id is not None
    assert source.name == "Thomson Scattering"
    assert source.description == "Measures Te and ne profiles."

    db_source = session.get(Source, source.id)
    assert db_source is not None
    assert db_source.name == "Thomson Scattering"


def test_create_duplicate_source_fails(session: Session):
    service = SourceService(session)
    service.create(SourceCreate(name="Unique Source"))

    with pytest.raises(IntegrityError):
        service.create(SourceCreate(name="Unique Source"))


def test_get_source(session: Session):
    service = SourceService(session)
    created_source = service.create(SourceCreate(name="ECE"))

    retrieved_source = service.get(created_source.id)
    assert retrieved_source is not None
    assert retrieved_source.id == created_source.id
    assert retrieved_source.name == "ECE"


def test_get_source_not_found(session: Session):
    service = SourceService(session)
    retrieved_source = service.get(999)
    assert retrieved_source is None


def test_get_sources(session: Session):
    service = SourceService(session)
    service.create(SourceCreate(name="Source 1"))
    service.create(SourceCreate(name="Source 2"))

    sources = service.get_multi()
    assert len(sources) == 2


def test_get_sources_with_limit_and_offset(session: Session):
    service = SourceService(session)
    for i in range(10):
        service.create(SourceCreate(name=f"Source {i}"))

    sources_limited = service.get_multi(limit=5)
    assert len(sources_limited) == 5

    sources_offset = service.get_multi(offset=5, limit=5)
    assert len(sources_offset) == 5
    assert sources_offset[0].name == "Source 5"


def test_update_source(session: Session):
    service = SourceService(session)
    source = service.create(SourceCreate(name="Initial Name"))

    updated_source = service.update(source.id, SourceUpdate(name="Updated Name"))
    assert updated_source is not None
    assert updated_source.name == "Updated Name"


def test_update_source_not_found(session: Session):
    service = SourceService(session)
    updated_source = service.update(999, SourceUpdate(name="Non Existent"))
    assert updated_source is None


def test_delete_source(session: Session):
    service = SourceService(session)
    source = service.create(SourceCreate(name="ToDelete"))

    service.delete(source.id)

    db_source = session.get(Source, source.id)
    assert db_source is None


def test_delete_source_not_found(session: Session):
    service = SourceService(session)
    deleted_source = service.delete(999)
    assert deleted_source is False
