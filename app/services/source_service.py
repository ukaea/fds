from sqlmodel import Session

from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.base_service import BaseService


class SourceService(BaseService[Source, SourceCreate, SourceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Source, session=session)
