from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth.access_control import (
    EffectivePolicy,
    get_effective_access_level,
    get_effective_policy,
    validate_policy_fields,
)
from app.auth.permissions import check_is_admin
from app.core.audit import record_restricted_read
from app.core.context import ReadTier, record_returned
from app.core.naming import normalise_device_name
from app.models.device import Device, DeviceCreate, DeviceRead, DeviceUpdate
from app.models.identity import ANONYMOUS_USER, AuthenticatedUser
from app.models.policy import AccessLevel
from app.services.base_service import BaseService
from app.services.exceptions import ConflictError, DeviceNotFoundError, ForbiddenError


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
        policy = get_effective_policy(device, self.session)
        self._enforce_read_policy(policy, user)
        record_restricted_read(device, policy.access_level, tier)

    def _enforce_read_policy(
        self, policy: EffectivePolicy, user: AuthenticatedUser
    ) -> None:
        """Enforce read access for Device metadata.

        Resolves the effective policy (``access_level``, ``required_scopes``,
        ``allowed_idps``) for the Device, with the global default as fallback.

        - PUBLIC / EMBARGOED: metadata is discoverable by everyone (EMBARGOED
          restricts data, not metadata — enforced at credential vending).
        - RESTRICTED: requires an authenticated user, then any IdP and scope
          gates set by the policy. With no explicit ``required_scopes`` an
          authenticated user from a trusted IdP suffices (no capability check
          for metadata reads — that belongs to credential vending).

        Raises ``ForbiddenError`` when the user does not satisfy the policy.
        """
        if policy.access_level in (AccessLevel.PUBLIC, AccessLevel.EMBARGOED):
            return

        if user.is_anonymous:
            raise ForbiddenError("Authentication required for this resource")

        if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
            raise ForbiddenError(
                "Access denied: your identity provider is not permitted "
                "for this resource"
            )

        if policy.required_scopes is not None:
            for scope in policy.required_scopes:
                if scope not in user.scopes:
                    raise ForbiddenError(f"Not authorized, requires scope: {scope}")

    def get_multi(
        self,
        *,
        user: AuthenticatedUser | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Device]:
        """Get devices with metadata visibility filtering applied."""
        devices = list(super().get_multi(offset=offset, limit=limit))
        if user is None:
            user = ANONYMOUS_USER

        accessible_devices: list[Device] = []

        for device in devices:
            try:
                self.check_read_access(device, user, ReadTier.LISTED)
                accessible_devices.append(device)
            except ForbiddenError:
                continue

        record_returned(len(accessible_devices))
        return accessible_devices

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
        self.session.delete(device)
        self.session.commit()
        return True

    def to_read_model(self, device: Device) -> DeviceRead:
        """
        Converts a Device ORM object to a DeviceRead DTO, including the effective access level.
        """
        read_model = DeviceRead.model_validate(device)
        read_model.effective_access_level = get_effective_access_level(
            device, self.session
        )
        return read_model
