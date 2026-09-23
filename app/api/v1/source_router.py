from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import CollectionServiceDep, CurrentUserDep, SourceServiceDep
from app.models.collection import CollectionRead
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


@router.get("/{name}/collections", response_model=list[CollectionRead])
def read_collections_for_source(
    name: str,
    collection_service: CollectionServiceDep,
    user: CurrentUserDep,
    offset: int = 0,
    limit: int = 100,
) -> Sequence[CollectionRead]:
    """
    Return all Collections whose linked Activity was produced by the named Source.
    """
    collections = collection_service.get_for_source(
        source_name=name, user=user, offset=offset, limit=limit
    )
    return [collection_service.to_read_model(c) for c in collections]


@router.get("/id/{id}", response_model=SourceRead)
def read_source_by_id(id: int, source_service: SourceServiceDep) -> SourceRead:
    """Retrieve a single source by its internal integer ID.

    This is the URI the semantic projection names a Source by, so it has to
    resolve: a dangling identifier is worse than none.
    """
    source = source_service.get(id)
    if not source:
        raise ResourceNotFoundError(f"Source {id} not found")
    return source_service.to_read_model(source)


@router.get("/{name}", response_model=SourceRead)
def read_source_by_name(name: str, source_service: SourceServiceDep) -> SourceRead:
    """
    Retrieve a single source by its descriptive name.
    """
    source = source_service.get_by_name(name)
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
    source_service.delete(id, user)
