from sqlmodel import Session, select

from app.auth.permissions import check_is_admin
from app.models.identity import AuthenticatedUser
from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.base_service import BaseService
from app.services.exceptions import ResourceNotFoundError


class SourceService(BaseService[Source, SourceCreate, SourceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Source, session=session)

    def create(self, obj_in: SourceCreate, user: AuthenticatedUser) -> Source:
        """
        Create a new source.
        """
        check_is_admin(user)
        return super().create(obj_in)

    def update(
        self, *, db_obj: Source, obj_in: SourceUpdate, user: AuthenticatedUser
    ) -> Source:
        """
        Update a source.
        """
        check_is_admin(user)
        return super().update(db_obj=db_obj, obj_in=obj_in)

    def delete_with_auth(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a source with authorization.
        """
        check_is_admin(user)
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Source {id} not found")
        return self.delete(id)

    def get_by_name(self, name: str) -> Source | None:
        """
        Retrieve a source by its unique name.
        """
        statement = select(Source).where(Source.name == name)
        return self.session.exec(statement).first()
