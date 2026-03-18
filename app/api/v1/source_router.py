from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, SourceServiceDep
from app.models.source import SourceCreate, SourceRead, SourceUpdate
from app.services.exceptions import ResourceNotFoundError

router = APIRouter()


@router.post("/", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    *,
    source_in: SourceCreate,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> SourceRead:
    """
    Create a new source. Requires global admin.
    """
    source = source_service.create(source_in, user)
    return source_service.to_read_model(source)


@router.get("/", response_model=list[SourceRead])
def read_sources(
    source_service: SourceServiceDep, offset: int = 0, limit: int = 100
) -> Sequence[SourceRead]:
    """
    Retrieve all sources.
    """
    sources = source_service.get_multi(offset=offset, limit=limit)
    return source_service.to_read_models(sources)


@router.get("/{name}", response_model=SourceRead)
def read_source_by_name(name: str, source_service: SourceServiceDep) -> SourceRead:
    """
    Retrieve a single source by its descriptive name.
    """
    source = source_service.get_by_name(name)
    if not source:
        raise ResourceNotFoundError(f"Source {name} not found")
    return source_service.to_read_model(source)


@router.put("/{id}", response_model=SourceRead)
def update_source(
    *,
    id: int,
    source_in: SourceUpdate,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> SourceRead:
    """
    Update a source. Requires global admin.
    """
    source = source_service.update(id=id, obj_in=source_in, user=user)
    return source_service.to_read_model(source)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    *,
    id: int,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete a source. Requires global admin.
    """
    source_service.delete_with_auth(id, user)
    return None
