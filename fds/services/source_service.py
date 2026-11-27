from collections.abc import Sequence

from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from fds.auth.access_control import (
    check_create,
    check_policy_update,
    check_read,
    check_write,
    validate_allowed_idps,
)
from fds.auth.permissions import check_sets_write_roles
from fds.core.naming import normalise_device_name
from fds.models.activity import Activity
from fds.models.device import Device
from fds.models.identity import AuthenticatedUser
from fds.models.source import Source, SourceCreate, SourceRead, SourceUpdate
from fds.services.base_service import BaseService
from fds.services.exceptions import (
    ConflictError,
    DeviceNotFoundError,
    ResourceNotFoundError,
)
from fds.services.visibility import read_page, readable_clause, readable_only


def activity_source_ids(activity: Activity) -> set[int]:
    """The ids of every Source ``activity`` names: its executor, instruments,
    agents and the agents in its delegations."""
    ids = {activity.source_id} if activity.source_id is not None else set()
    ids |= {source.id for source in activity.instruments if source.id is not None}
    ids |= {link.source_id for link in activity.agent_links}
    for link in activity.delegation_links:
        ids |= {link.subordinate_source, link.responsible_source}
    return ids


def readable_source_ids(
    session: Session, source_ids: set[int], user: AuthenticatedUser
) -> set[int]:
    """The ids among ``source_ids`` of the Sources ``user`` may read."""
    if not source_ids:
        return set()
    sources = session.exec(select(Source).where(col(Source.id).in_(source_ids))).all()
    return {s.id for s in readable_only(session, sources, user) if s.id is not None}


def readable_source_clause(
    session: Session, name: str | None, user: AuthenticatedUser
) -> ColumnElement[bool] | None:
    """A clause keeping the Source called ``name`` if ``user`` may read it, for a
    listing's ``source`` filter. None when the listing names no Source."""
    if name is None:
        return None
    return readable_clause(
        session, Source, user, select(Source).where(Source.name == name)
    )


def readable_activity_sources(
    session: Session, activities: Sequence[Activity | None], user: AuthenticatedUser
) -> set[int]:
    """The ids of the Sources ``user`` may read among those ``activities`` name.

    The Sources of every Activity are checked together.
    """
    named: set[int] = set()
    for activity in activities:
        if activity is not None:
            named |= activity_source_ids(activity)
    return readable_source_ids(session, named, user)


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
        Create a new source. A source linked to a device needs one of the
        device's write roles; one linked to no device needs fds-admin.
        """
        validate_allowed_idps(obj_in.allowed_idps)
        device_id = None
        obj_in.device_name = normalise_device_name(obj_in.device_name)
        if obj_in.device_name:
            device = self.session.exec(
                select(Device).where(Device.name == obj_in.device_name)
            ).first()
            if not device:
                raise DeviceNotFoundError(f"Device '{obj_in.device_name}' not found")
            device_id = device.id
        check_create(self.session, user, obj_in.device_name)
        check_sets_write_roles(user, obj_in.write_roles)

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

        check_write(db_obj, self.session, user)
        check_policy_update(user, db_obj, obj_in.model_dump(exclude_unset=True))
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, id: int, user: AuthenticatedUser) -> bool:
        """Delete a source with authorization."""
        db_obj = self.get(id)
        if not db_obj:
            raise ResourceNotFoundError(f"Source {id} not found")

        check_write(db_obj, self.session, user)
        return self.delete_unchecked(id)

    def get_readable_or_raise(self, id: int, user: AuthenticatedUser) -> Source:
        """The Source with ``id``, if ``user`` may read it."""
        source = self.get(id)
        if not source:
            raise ResourceNotFoundError(f"Source {id} not found")
        check_read(source, self.session, user)
        return source

    def get_readable(
        self,
        user: AuthenticatedUser,
        *,
        offset: int = 0,
        limit: int = 100,
        name: str | None = None,
    ) -> Sequence[Source]:
        """A page of the sources ``user`` may read in id order, only the one called
        ``name`` if given."""
        statement = select(Source).order_by(col(Source.id))
        if name is not None:
            statement = statement.where(Source.name == name)
        return read_page(
            self.session, Source, statement, user, offset=offset, limit=limit
        )

    def get_for_device(
        self,
        device_name: str,
        user: AuthenticatedUser,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[Source]:
        """
        Retrieve sources associated with a specific device by name.
        """
        device = self.session.exec(
            select(Device).where(Device.name == normalise_device_name(device_name))
        ).first()
        if not device:
            raise DeviceNotFoundError(f"Device '{device_name}' not found")
        statement = (
            select(Source).where(Source.device_id == device.id).order_by(col(Source.id))
        )
        return read_page(
            self.session, Source, statement, user, offset=offset, limit=limit
        )
