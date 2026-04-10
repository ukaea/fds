from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.config import config
from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.services.exceptions import FDSValidationError

DEFAULT_ACCESS_LEVEL = AccessLevel.RESTRICTED


@dataclass
class EffectivePolicy:
    """
    Resolved authorization policy for a dataset (or shot/device), after walking the
    Dataset → Shot → Device inheritance chain.

    access_level:   The effective visibility / auth baseline.
    required_scopes:
        None  → no explicit scope policy; service falls back to capability checks.
        []    → authenticated user from an allowed IdP is sufficient (auth-only gate).
        [..] → all listed scopes must be present in the user's token.
    allowed_idps:
        None  → any issuer that is globally trusted is accepted.
        [..] → user's issuer must appear in this list (subset of TRUSTED_IDPS).
    """

    access_level: AccessLevel
    required_scopes: list[str] | None
    allowed_idps: list[str] | None


def get_effective_access_level(
    obj: Collection | Dataset | Shot | Device, session: Session
) -> AccessLevel:
    """
    Calculates the effective access level for an object based on inheritance.

    Specific overrides general. The resolution order is:
    Collection/Dataset → Shot → Device → Global Default

    Collections follow the same inheritance chain as Datasets: if no
    ``access_level`` is set directly, the enclosing Shot's policy is checked,
    then the Device's, and finally the global default is applied.
    """
    # 1. Direct override
    if obj.access_level:
        return obj.access_level

    # 2. Inherit from Shot (if applicable)
    if isinstance(obj, (Dataset, Collection)) and obj.shot_id and obj.device_name:
        shot = session.get(Shot, (obj.device_name, obj.shot_id))
        if shot:
            return get_effective_access_level(shot, session)

    # 3. Inherit from Device
    device = None
    if isinstance(obj, (Dataset, Collection, Shot)) and obj.device_name:
        statement = select(Device).where(Device.name == obj.device_name)
        device = session.exec(statement).first()

    if device:
        return get_effective_access_level(device, session)

    # 4. Fallback to Global Default
    return DEFAULT_ACCESS_LEVEL


def _get_inherited_list_field(
    obj: Collection | Dataset | Shot | Device,
    field_name: str,
    session: Session,
) -> list[str] | None:
    """
    Walk Collection/Dataset → Shot → Device returning the first explicitly-set
    list field (``required_scopes`` or ``allowed_idps``).

    Returns ``None`` if the field is unset at every level of the hierarchy.
    Collections follow the same resolution chain as Datasets.
    """
    val: list[str] | None = getattr(obj, field_name, None)
    if val is not None:
        return val

    if isinstance(obj, (Dataset, Collection)):
        # Try shot first (composite key: device_name + shot_id)
        if obj.shot_id and obj.device_name:
            shot = session.get(Shot, (obj.device_name, obj.shot_id))
            if shot:
                val = _get_inherited_list_field(shot, field_name, session)
                if val is not None:
                    return val
        # Fallthrough to device
        if obj.device_name:
            stmt = select(Device).where(Device.name == obj.device_name)
            device = session.exec(stmt).first()
            if device:
                return _get_inherited_list_field(device, field_name, session)

    elif isinstance(obj, Shot) and obj.device_name:
        stmt = select(Device).where(Device.name == obj.device_name)
        device = session.exec(stmt).first()
        if device:
            return _get_inherited_list_field(device, field_name, session)

    return None


def get_effective_policy(
    obj: Collection | Dataset | Shot | Device, session: Session
) -> EffectivePolicy:
    """
    Returns the fully-resolved EffectivePolicy for a dataset (or shot/device),
    inheriting required_scopes and allowed_idps from the hierarchy.
    """
    return EffectivePolicy(
        access_level=get_effective_access_level(obj, session),
        required_scopes=_get_inherited_list_field(obj, "required_scopes", session),
        allowed_idps=_get_inherited_list_field(obj, "allowed_idps", session),
    )


def validate_policy_fields(
    access_level: AccessLevel | None,
    required_scopes: list[str] | None,
    allowed_idps: list[str] | None,
) -> None:
    """
    Validates that policy fields form a consistent combination.
    Must be called before writing a Dataset, Shot, or Device.

    Invariants:
    - PUBLIC cannot have required_scopes or allowed_idps.
    - A null access_level cannot carry required_scopes or allowed_idps
      (those fields require an explicit level to be meaningful).
    - allowed_idps, when set, must be non-empty and every entry must match
      an issuer in the globally-configured TRUSTED_IDPS.
        - allowed_idps validation requires a non-empty TRUSTED_IDPS configuration.
    """
    if access_level == AccessLevel.PUBLIC:
        if required_scopes is not None:
            raise FDSValidationError("PUBLIC resources cannot have required_scopes")
        if allowed_idps is not None:
            raise FDSValidationError("PUBLIC resources cannot have allowed_idps")

    if access_level is None:
        if required_scopes is not None:
            raise FDSValidationError(
                "required_scopes requires an explicit access_level "
                "(cannot be combined with an inherited access level)"
            )
        if allowed_idps is not None:
            raise FDSValidationError(
                "allowed_idps requires an explicit access_level "
                "(cannot be combined with an inherited access level)"
            )

    if allowed_idps is not None:
        if len(allowed_idps) == 0:
            raise FDSValidationError(
                "allowed_idps must not be an empty list; "
                "use None to permit any trusted IdP"
            )

        trusted_idps = getattr(config, "TRUSTED_IDPS", None)
        if not trusted_idps:
            raise FDSValidationError(
                "allowed_idps cannot be validated because TRUSTED_IDPS is "
                "missing or empty"
            )

        trusted_issuers = {idp.issuer for idp in trusted_idps}

        for ref in allowed_idps:
            if ref not in trusted_issuers:
                raise FDSValidationError(
                    f"allowed_idps contains unknown IdP issuer: '{ref}'. "
                    "Each entry must match a configured TRUSTED_IDPS issuer."
                )
