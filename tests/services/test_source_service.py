import pytest
from sqlmodel import Session

from app.auth.security import AuthenticatedUser
from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.exceptions import ResourceNotFoundError
from app.services.source_service import SourceService


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

    from app.services.exceptions import ConflictError

    with pytest.raises(ConflictError):
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

    updated_source = service.update(
        id=source.id, obj_in=SourceUpdate(name="Updated Name"), user=admin_user
    )
    assert updated_source is not None
    assert updated_source.name == "Updated Name"


def test_delete_source(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    source = service.create(SourceCreate(name="ToDelete"), user=admin_user)

    assert source.id is not None
    service.delete(source.id, user=admin_user)

    db_source = session.get(Source, source.id)
    assert db_source is None


def test_delete_source_not_found(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    with pytest.raises(ResourceNotFoundError):
        service.delete(999, user=admin_user)


def test_get_source_by_name(session: Session, admin_user: AuthenticatedUser):
    service = SourceService(session)
    service.create(SourceCreate(name="UniqueName"), user=admin_user)

    retrieved = service.get_by_name("UniqueName")
    assert retrieved is not None
    assert retrieved.name == "UniqueName"


def test_get_source_by_name_not_found(session: Session):
    service = SourceService(session)
    assert service.get_by_name("NonExistent") is None


def test_create_source_device_admin(
    session: Session, admin_user: AuthenticatedUser, mast_admin_user: AuthenticatedUser
):
    from app.models.device import DeviceCreate
    from app.services.device_service import DeviceService

    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Test"), user=admin_user
    )

    service = SourceService(session)
    source = service.create(
        SourceCreate(name="MastSource", device_name="MAST"), user=mast_admin_user
    )
    assert source.id is not None
    assert source.name == "MastSource"


def test_create_source_unauthorized(
    session: Session, admin_user: AuthenticatedUser, mast_admin_user: AuthenticatedUser
):
    from app.models.device import DeviceCreate
    from app.services.device_service import DeviceService
    from app.services.exceptions import ForbiddenError

    DeviceService(session).create(
        DeviceCreate(name="JET", type="Test"), user=admin_user
    )

    service = SourceService(session)
    with pytest.raises(ForbiddenError):
        service.create(
            SourceCreate(name="JetSource", device_name="JET"), user=mast_admin_user
        )


def test_update_source_device_admin(
    session: Session, admin_user: AuthenticatedUser, mast_admin_user: AuthenticatedUser
):
    from app.models.device import DeviceCreate
    from app.services.device_service import DeviceService

    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Test"), user=admin_user
    )

    service = SourceService(session)
    source = service.create(
        SourceCreate(name="MastSourceForUpdate", device_name="MAST"), user=admin_user
    )
    assert source.id is not None

    updated = service.update(
        id=source.id,
        obj_in=SourceUpdate(name="UpdatedMastSource"),
        user=mast_admin_user,
    )
    assert updated.name == "UpdatedMastSource"


def test_delete_source_device_admin(
    session: Session, admin_user: AuthenticatedUser, mast_admin_user: AuthenticatedUser
):
    from app.models.device import DeviceCreate
    from app.services.device_service import DeviceService

    DeviceService(session).create(
        DeviceCreate(name="MAST", type="Test"), user=admin_user
    )

    service = SourceService(session)
    source = service.create(
        SourceCreate(name="MastSourceForDelete", device_name="MAST"), user=admin_user
    )
    assert source.id is not None

    assert service.delete_with_auth(id=source.id, user=mast_admin_user) is True
    assert service.get(source.id) is None
