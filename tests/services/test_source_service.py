import pytest
from sqlmodel import Session
from sqlalchemy.exc import IntegrityError

from app.models.source import Source, SourceCreate
from app.services.source_service import SourceService


def test_create_source(session: Session):
    service = SourceService(session)
    source_create = SourceCreate(name="Thomson Scattering", description="Measures Te and ne profiles.")
    source = service.create_source(source_create)

    assert source.id is not None
    assert source.name == "Thomson Scattering"
    assert source.description == "Measures Te and ne profiles."

    db_source = session.get(Source, source.id)
    assert db_source is not None
    assert db_source.name == "Thomson Scattering"


def test_create_duplicate_source_fails(session: Session):
    service = SourceService(session)
    source1 = SourceCreate(name="Unique Source")
    service.create_source(source1)

    source2 = SourceCreate(name="Unique Source")
    with pytest.raises(IntegrityError):
        service.create_source(source2)


def test_get_source(session: Session):
    service = SourceService(session)
    created_source = service.create_source(SourceCreate(name="ECE"))
    assert created_source.id is not None

    retrieved_source = service.get_source(created_source.id)
    assert retrieved_source is not None
    assert retrieved_source.id == created_source.id
    assert retrieved_source.name == "ECE"


def test_get_sources(session: Session):
    service = SourceService(session)
    service.create_source(SourceCreate(name="Source 1"))
    service.create_source(SourceCreate(name="Source 2"))

    sources = service.get_sources()
    assert len(sources) == 2


def test_delete_source(session: Session):
    service = SourceService(session)
    source_to_delete = service.create_source(SourceCreate(name="ToDelete"))
    assert source_to_delete.id is not None

    result = service.delete_source(source_to_delete.id)
    assert result is True

    db_source = session.get(Source, source_to_delete.id)
    assert db_source is None
