from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.permissions import check_device_admin, check_is_admin
from app.models.device import Device
from app.models.identity import AuthenticatedUser
from app.models.source import Source, SourceCreate, SourceRead, SourceUpdate
from app.services.base_service import BaseService
from app.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    ResourceNotFoundError,
)


class SourceService(BaseService[Source, SourceCreate, SourceUpdate]):
    def __init__(self, session: Session):
        super().__init__(model=Source, session=session)

    def to_read_model(self, source: Source) -> SourceRead:
        """Convert a Source ORM model to a SourceRead model with device_name."""
        source_data = source.model_dump()
        source_data["device_name"] = source.device.name if source.device else None
        return SourceRead.model_validate(source_data)

    def to_read_models(self, sources: Sequence[Source]) -> list[SourceRead]:
        return [self.to_read_model(source) for source in sources]

    def create(self, obj_in: SourceCreate, user: AuthenticatedUser) -> Source:
        """
        Create a new source.
        """
        device_id = None
        if obj_in.device_name:
            device = self.session.exec(
                select(Device).where(Device.name == obj_in.device_name)
            ).first()
            if not device:
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")
            device_id = device.id
            check_device_admin(user, obj_in.device_name)
        else:
            check_is_admin(user)

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
        self, *, id: int, obj_in: SourceUpdate, user: AuthenticatedUser
    ) -> Source:
        """
        Update a source. Resolves the source by ID internally.
        """
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Source {id} not found")

        if db_obj.device:
            check_device_admin(user, db_obj.device.name)
        else:
            check_is_admin(user)
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """Delete a source with authorization."""
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Source {id} not found")

        if db_obj.device:
            check_device_admin(user, db_obj.device.name)
        else:
            check_is_admin(user)
        return self.delete_unchecked(id)

    def get_by_name(self, name: str) -> Source:
        """Resolve a source by name.

        Raises ``ResourceNotFoundError`` if the source does not exist.
        """
        statement = select(Source).where(Source.name == name)
        source = self.session.exec(statement).first()
        if not source:
            raise ResourceNotFoundError(f"Source '{name}' not found")
        return source

    def get_for_device(
        self, device_name: str, offset: int = 0, limit: int = 100
    ) -> Sequence[Source]:
        """
        Retrieve sources associated with a specific device by name.
        """
        device = self.session.exec(
            select(Device).where(Device.name == device_name)
        ).first()
        if not device:
            raise DeviceNotFoundError(f"Device '{device_name}' not found")
        statement = (
            select(Source)
            .where(Source.device_id == device.id)
            .offset(offset)
            .limit(limit)
        )
        return self.session.exec(statement).all()
