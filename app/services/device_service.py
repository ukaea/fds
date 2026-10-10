from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app.auth.access_control import (
    check_read,
    get_effective_access_level,
    validate_policy_fields,
)
from app.auth.permissions import check_is_admin
from app.core.context import ReadTier
from app.core.naming import normalise_device_name
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.shot import Shot
from app.models.source import Source
from app.services.base_service import BaseService
from app.services.exceptions import ConflictError, DeviceNotFoundError
from app.services.visibility import read_page


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate]):
    """
    Service for device CRUD operations.

    Devices are identified externally by *name* (e.g. "MAST", "JET").
    Names are case-insensitive: they are stored lower-cased and every lookup
    normalises its input, so ``title`` carries the canonical display form.
    The surrogate ``id`` column is a persistence detail for ORM relations;
    it is not a valid retrieval key at the service boundary.
    Use ``get_by_name`` for all external lookups.
    """

    def __init__(self, session: Session):
        super().__init__(model=Device, session=session)

    def get(self, id: object) -> Device:
        raise NotImplementedError(
            "DeviceService does not support lookup by id. "
            "Use get_by_name(name, user) instead."
        )

    def check_read_access(
        self,
        device: Device,
        user: AuthenticatedUser,
        tier: ReadTier = ReadTier.READ,
    ) -> None:
        """Enforce read access, and record it when the resource is not public."""
        check_read(device, self.session, user, tier)

    def get_multi(
        self,
        *,
        user: AuthenticatedUser = ANONYMOUS_USER,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Device]:
        """Get devices with metadata visibility filtering applied."""
        statement = select(Device).order_by(col(Device.id))
        return read_page(
            self.session, Device, statement, user, offset=offset, limit=limit
        )

    def get_by_name(
        self,
        name: str,
        user: AuthenticatedUser = ANONYMOUS_USER,
    ) -> Device:
        """Resolve a device by name, enforcing read access.

        Raises ``DeviceNotFoundError`` if the device does not exist.
        Raises ``ForbiddenError`` if ``user`` lacks read access.
        """
        device = self._get_by_name(name)
        self.check_read_access(device, user)
        return device

    def _get_by_name(self, name: str) -> Device:
        """Internal lookup by name with no access check.

        Used by admin mutation paths (update/delete) where read policy
        should not gate the operation.  Raises ``DeviceNotFoundError``
        if the device does not exist.
        """
        result = self.session.exec(
            select(Device).where(Device.name == normalise_device_name(name))
        )
        device = result.first()
        if not device:
            raise DeviceNotFoundError(f"Device '{name}' not found")
        return device

    def create(self, obj_in: DeviceCreate, user: AuthenticatedUser) -> Device:
        """
        Create a new device. Requires global admin privileges.
        """
        validate_policy_fields(
            obj_in.access_level,
            obj_in.required_scopes,
            obj_in.allowed_idps,
        )
        check_is_admin(user)
        obj_in.name = cast(str, normalise_device_name(obj_in.name))
        try:
            return self.create_unchecked(obj_in)
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError(f"Device '{obj_in.name}' already exists") from e

    def update(
        self,
        *,
        device_name: str,
        obj_in: DeviceUpdate,
        user: AuthenticatedUser,
    ) -> Device:
        """
        Update a device by name. Requires global admin privileges.
        Resolves the device internally.
        """
        check_is_admin(user)
        db_obj = self._get_by_name(device_name)
        if obj_in.name is not None:
            obj_in.name = normalise_device_name(obj_in.name)
        update_data = obj_in.model_dump(exclude_unset=True)
        validate_policy_fields(
            update_data.get("access_level", db_obj.access_level),
            update_data.get("required_scopes", db_obj.required_scopes),
            update_data.get("allowed_idps", db_obj.allowed_idps),
        )
        return self.update_unchecked(db_obj=db_obj, obj_in=obj_in)

    def delete(self, device_name: str, user: AuthenticatedUser) -> bool:
        """
        Delete a device by name. Requires global admin privileges.
        """
        check_is_admin(user)
        device = self._get_by_name(device_name)
        self._reject_if_occupied(device)
        self.session.delete(device)
        self.session.commit()
        return True

    def _reject_if_occupied(self, device: Device) -> None:
        shots = self.session.exec(
            select(func.count())
            .select_from(Shot)
            .where(Shot.device_name == device.name)
        ).one()
        sources = self.session.exec(
            select(func.count())
            .select_from(Source)
            .where(Source.device_id == device.id)
        ).one()

        held = [
            f"{count} {noun if count == 1 else noun + 's'}"
            for count, noun in ((shots, "shot"), (sources, "source"))
            if count
        ]
        if held:
            raise ConflictError(
                f"Device '{device.name}' holds {' and '.join(held)}, "
                "which would be deleted with it."
            )

    def to_read_model(self, device: Device) -> DeviceRead:
        """
        Converts a Device ORM object to a DeviceRead DTO, including the effective access level.
        """
        read_model = DeviceRead.model_validate(device)
        read_model.effective_access_level = get_effective_access_level(
            device, self.session
        )
        return read_model
