import pytest
from sqlmodel import Session
from sqlalchemy.exc import IntegrityError

from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.source_service import SourceService
from app.services.exceptions import ResourceNotFoundError


from app.auth.security import AuthenticatedUser


def test_create_source(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    source_create = SourceCreate(
        name="Thomson Scattering", description="Measures Te and ne profiles."
    )
    source = service.create(source_create, user=admin_user)

    assert source.id is not None
    assert source.name == "Thomson Scattering"
    assert source.description == "Measures Te and ne profiles."

    db_source = session.get(Source, source.id)
    assert db_source is not None
    assert db_source.name == "Thomson Scattering"


def test_create_duplicate_source_fails(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    service.create(SourceCreate(name="Unique Source"), user=admin_user)

    with pytest.raises(IntegrityError):
        service.create(SourceCreate(name="Unique Source"), user=admin_user)


def test_get_source(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    created_source = service.create(SourceCreate(name="ECE"), user=admin_user)

    retrieved_source = service.get(created_source.id)
    assert retrieved_source is not None
    assert retrieved_source.id == created_source.id
    assert retrieved_source.name == "ECE"


def test_get_source_not_found(session: Session):
    service = SourceService(session)
    retrieved_source = service.get(999)
    assert retrieved_source is None


def test_get_sources(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    service.create(SourceCreate(name="Source 1"), user=admin_user)
    service.create(SourceCreate(name="Source 2"), user=admin_user)

    sources = service.get_multi()
    assert len(sources) == 2


def test_get_sources_with_limit_and_offset(
    session: Session, admin_user: AuthenticatedUser
):
    service = SourceService(session)
    for i in range(10):
        service.create(SourceCreate(name=f"Source {i}"), user=admin_user)

    sources_limited = service.get_multi(limit=5)
    assert len(sources_limited) == 5

    sources_offset = service.get_multi(offset=5, limit=5)
    assert len(sources_offset) == 5
    assert sources_offset[0].name == "Source 5"


def test_update_source(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    source = service.create(SourceCreate(name="Initial Name"), user=admin_user)
    assert source.id is not None
    db_source = service.get(source.id)
    assert db_source is not None

    updated_source = service.update(
        db_obj=db_source, obj_in=SourceUpdate(name="Updated Name"), user=admin_user
    )
    assert updated_source is not None
    assert updated_source.name == "Updated Name"


def test_delete_source(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    source = service.create(SourceCreate(name="ToDelete"), user=admin_user)

    service.delete_with_auth(source.id, user=admin_user)

    db_source = session.get(Source, source.id)
    assert db_source is None


def test_delete_source_not_found(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    with pytest.raises(ResourceNotFoundError):
        service.delete_with_auth(999, user=admin_user)


def test_get_source_by_name(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    service.create(SourceCreate(name="UniqueName"), user=admin_user)

    retrieved = service.get_by_name("UniqueName")
    assert retrieved is not None
    assert retrieved.name == "UniqueName"


def test_get_source_by_name_not_found(session: Session):
    service = SourceService(session)
    assert service.get_by_name("NonExistent") is None
