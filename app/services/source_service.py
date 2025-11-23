from collections.abc import Sequence
from sqlmodel import Session, select

from app.models.source import Source, SourceCreate, SourceUpdate


class SourceService:
    def __init__(self, session: Session):
        self.session = session

    def create_source(self, source_create: SourceCreate) -> Source:
        source = Source.model_validate(source_create)
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def get_source(self, source_id: int) -> Source | None:
        return self.session.get(Source, source_id)

    def get_sources(self, offset: int = 0, limit: int = 100) -> Sequence[Source]:
        statement = select(Source).offset(offset).limit(limit)
        results = self.session.exec(statement)
        sources = results.all()
        return sources

    def update_source(self, source_id: int, source_update: SourceUpdate) -> Source | None:
        source = self.session.get(Source, source_id)
        if not source:
            return None
        
        update_data = source_update.model_dump(exclude_unset=True)
        source.sqlmodel_update(update_data)
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def delete_source(self, source_id: int) -> bool:
        source = self.session.get(Source, source_id)
        if not source:
            return False
        self.session.delete(source)
        self.session.commit()
        return True
