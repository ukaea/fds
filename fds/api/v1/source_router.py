from collections.abc import Sequence

from fastapi import APIRouter, status

from fds.api.deps import (
    DEFAULT_PAGE_SIZE,
    CurrentUserDep,
    Limit,
    Offset,
    SourceServiceDep,
)
from fds.models.source import SourceCreate, SourceRead, SourceUpdate
from fds.services.exceptions import ResourceNotFoundError

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
    source_service: SourceServiceDep,
    offset: Offset = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
    name: str | None = None,
) -> Sequence[SourceRead]:
    """
    Retrieve all sources.

    `name` keeps the source with that name. Source names are unique, so the
    page holds one source, or none if no source has that name.
    """
    sources = source_service.get_multi(offset=offset, limit=limit, name=name)
    return source_service.to_read_models(sources)


@router.get("/{id:int}", response_model=SourceRead)
def read_source(id: int, source_service: SourceServiceDep) -> SourceRead:
    """Retrieve a single source by its ID.

    To find a source by name, filter the listing: `GET /sources/?name=efit`.
    """
    source = source_service.get(id)
    if not source:
        raise ResourceNotFoundError(f"Source {id} not found")
    return source_service.to_read_model(source)


@router.patch("/{id:int}", response_model=SourceRead)
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


@router.delete("/{id:int}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    *,
    id: int,
    source_service: SourceServiceDep,
    user: CurrentUserDep,
) -> None:
    """
    Delete a source. Requires global admin.
    """
    source_service.delete(id, user)
