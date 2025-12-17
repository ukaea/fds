from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.models.source import Source, SourceCreate, SourceRead, SourceUpdate
from app.api.deps import SourceServiceDep

router = APIRouter()


@router.post("/", response_model=SourceRead)
def create_source(source_in: SourceCreate, source_service: SourceServiceDep) -> Source:
    """
    Create a new source.
    """
    source = source_service.create(source_in)
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


@router.get("/{source_id}", response_model=SourceRead)
def read_source(source_id: int, source_service: SourceServiceDep) -> Source:
    """
    Retrieve a single source by ID.
    """
    source = source_service.get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.put("/{source_id}", response_model=SourceRead)
def update_source(
    source_id: int, source_in: SourceUpdate, source_service: SourceServiceDep
) -> Source:
    """
    Update a source.
    """
    source = source_service.update(source_id, source_in)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/{source_id}")
def delete_source(source_id: int, source_service: SourceServiceDep) -> dict:
    """
    Delete a source.
    """
    source = source_service.delete(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"ok": True}
