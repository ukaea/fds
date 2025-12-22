from collections.abc import Sequence

from fastapi import APIRouter

from app.models.source import Source, SourceCreate, SourceRead, SourceUpdate
from app.api.deps import SourceServiceDep
from app.auth.security import get_current_user, AuthenticatedUser
from fastapi import Depends, status

router = APIRouter()


@router.post("/", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    *,
    source_in: SourceCreate,
    source_service: SourceServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Source:
    """
    Create a new source. Requires global admin.
    """
    source = source_service.create(source_in, user)
    return source


@router.get("/", response_model=list[SourceRead])
def read_sources(
    source_service: SourceServiceDep, offset: int = 0, limit: int = 100
) -> Sequence[Source]:
    """
    Retrieve all sources.
    """
    sources = source_service.get_multi(offset=offset, limit=limit)
    return sources


@router.get("/{name}", response_model=SourceRead)
def read_source_by_name(name: str, source_service: SourceServiceDep) -> Source:
    """
    Retrieve a single source by its descriptive name.
    """
    source = source_service.get_by_name(name)
    if not source:
        from app.services.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError(f"Source {name} not found")
    return source


@router.put("/{id}", response_model=SourceRead)
def update_source(
    *,
    id: int,
    source_in: SourceUpdate,
    source_service: SourceServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Source:
    """
    Update a source. Requires global admin.
    """
    db_source = source_service.get(id)
    if not db_source:
        from app.services.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError(f"Source {id} not found")
    source = source_service.update(db_obj=db_source, obj_in=source_in, user=user)
    return source


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    *,
    id: int,
    source_service: SourceServiceDep,
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """
    Delete a source. Requires global admin.
    """
    source_service.delete_with_auth(id, user)
    return None
