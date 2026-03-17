from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.permissions import check_is_admin
from app.models.identity import AuthenticatedUser
from app.models.source import Source, SourceCreate, SourceUpdate
from app.services.base_service import BaseService
from app.services.device_service import DeviceService
from app.services.exceptions import ConflictError, ResourceNotFoundError


class SourceService(BaseService[Source, SourceCreate, SourceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Source, session=session)

    def create(self, obj_in: SourceCreate, user: AuthenticatedUser) -> Source:
        """
        Create a new source.
        """
        check_is_admin(user)

        device_id = None
        if obj_in.device_name:
            device = DeviceService(self.session).get_by_name(obj_in.device_name)
            if not device:
                raise ResourceNotFoundError(f"Device '{obj_in.device_name}' not found")
            device_id = device.id

        # Convert to dict and exclude device_name since it's not in the Source table
        source_data = obj_in.model_dump(exclude={"device_name"})
        source_data["device_id"] = device_id

        db_obj = Source.model_validate(source_data)
        self.session.add(db_obj)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ConflictError(f"Source with name '{obj_in.name}' already exists")
        self.session.refresh(db_obj)
        return db_obj

    def update(
        self, *, db_obj: Source, obj_in: SourceUpdate, user: AuthenticatedUser
    ) -> Source:
        """
        Update a source.
        """
        check_is_admin(user)
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """
        Delete a source with authorization.
        """
        check_is_admin(user)
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Source {id} not found")
        return self.delete_unchecked(id)

    def get_by_name(self, name: str) -> Source | None:
        """
        Retrieve a source by its unique name.
        """
        statement = select(Source).where(Source.name == name)
        return self.session.exec(statement).first()

    def get_for_device(
        self, device_name: str, offset: int = 0, limit: int = 100
    ) -> Sequence[Source]:
        """
        Retrieve sources associated with a specific device by name.
        """
        device = DeviceService(self.session).get_by_name(device_name)
        if not device:
            raise ResourceNotFoundError(f"Device '{device_name}' not found")
        statement = (
            select(Source)
            .where(Source.device_id == device.id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
