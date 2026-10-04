from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.auth.permissions import check_device_admin, check_is_admin, check_shot_operator
from app.core.audit import record_restricted_read
from app.core.config import config
from app.core.context import ReadTier
from app.models.collection import Collection
from app.models.dataset import Dataset
from app.models.device import Device
from app.models.identity import AuthenticatedUser
from app.models.policy import AccessLevel
from app.models.shot import Shot
from app.services.exceptions import FDSValidationError, ForbiddenError

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


Policied = Collection | Dataset | Shot | Device

# The three fields that inherit. Each resolves independently: a Shot may set
# access_level while required_scopes still comes from its Device.
_POLICY_FIELDS = ("access_level", "required_scopes", "allowed_idps")


def policy_chain(obj: Policied, session: Session) -> list[Policied]:
    """``obj`` and the objects it inherits policy from, nearest first.

    Collection/Dataset → Shot → Device. A Collection or Dataset not attached to
    a shot inherits from its device directly, and a Device inherits from nothing
    because it has no ``device_name`` of its own.

    Walked once and returned as a list, because all three policy fields resolve
    over the same chain and loading it per field is where this used to spend its
    queries.
    """
    chain: list[Policied] = [obj]

    if isinstance(obj, (Dataset, Collection)) and obj.shot_id and obj.device_name:
        shot = session.get(Shot, (obj.device_name, obj.shot_id))
        if shot:
            chain.append(shot)

    device_name = getattr(obj, "device_name", None)
    if device_name:
        device = session.exec(select(Device).where(Device.name == device_name)).first()
        if device:
            chain.append(device)

    return chain


def _inherit(sources: Sequence[Any], field: str) -> Any:
    """The first explicitly-set value of ``field`` along ``sources``.

    ``None`` means "not set, keep looking"; every other value stops the walk,
    including an empty ``required_scopes``, which is a policy in its own right
    (any authenticated user from an allowed IdP) rather than an absence.
    """
    for source in sources:
        value = getattr(source, field, None)
        if value is not None:
            return value
    return None


def _policy_from(sources: Sequence[Any]) -> EffectivePolicy:
    """Resolve all three fields over one ordered list of policy sources."""
    access_level, required_scopes, allowed_idps = (
        _inherit(sources, field) for field in _POLICY_FIELDS
    )
    return EffectivePolicy(
        access_level=access_level or DEFAULT_ACCESS_LEVEL,
        required_scopes=required_scopes,
        allowed_idps=allowed_idps,
    )


def get_effective_policy(obj: Policied, session: Session) -> EffectivePolicy:
    """The policy that applies to ``obj``, after inheritance.

    Specific overrides general: the nearest explicitly-set value for each field
    wins, and an unset ``access_level`` anywhere in the chain falls back to
    ``DEFAULT_ACCESS_LEVEL``.
    """
    # A record that sets every policy field inherits nothing, so there is no
    # chain worth loading.
    if all(getattr(obj, field, None) is not None for field in _POLICY_FIELDS):
        return _policy_from([obj])
    return _policy_from(policy_chain(obj, session))


def get_effective_access_level(obj: Policied, session: Session) -> AccessLevel:
    """The effective access level for ``obj``, for callers wanting only that."""
    return get_effective_policy(obj, session).access_level


# A policy with nothing above it, so every unset field falls to the default.
NO_PARENT = EffectivePolicy(
    access_level=DEFAULT_ACCESS_LEVEL, required_scopes=None, allowed_idps=None
)


def read_denial(
    kind: type[Policied],
    policy: EffectivePolicy,
    user: AuthenticatedUser,
    device_name: str | None,
    in_shot: bool,
) -> str | None:
    """Why ``user`` may not read a ``kind`` record's metadata, or ``None`` if they may.

    Credentials for the record's data are decided separately, at vending.
    """
    if "fds-admin" in user.scopes:
        return None
    if policy.access_level in (AccessLevel.PUBLIC, AccessLevel.EMBARGOED):
        return None
    if user.is_anonymous:
        return "Authentication required for this resource"
    if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
        return (
            "Access denied: your identity provider is not permitted for this resource"
        )
    if policy.required_scopes is not None:
        for scope in policy.required_scopes:
            if scope not in user.scopes:
                return f"Not authorized, requires scope: {scope}"
        return None
    if kind in (Device, Shot):
        return None
    try:
        if device_name is None:
            check_is_admin(user)
        elif kind is Dataset and in_shot:
            check_shot_operator(user, device_name)
        else:
            check_device_admin(user, device_name)
    except ForbiddenError as denied:
        return str(denied)
    return None


def check_read(
    obj: Policied,
    session: Session,
    user: AuthenticatedUser,
    tier: ReadTier = ReadTier.READ,
) -> None:
    """Enforce read access to ``obj``, and record it when it is restricted."""
    policy = get_effective_policy(obj, session)
    denial = read_denial(
        type(obj),
        policy,
        user,
        getattr(obj, "device_name", None),
        bool(getattr(obj, "shot_id", None)),
    )
    if denial:
        raise ForbiddenError(denial)
    record_restricted_read(obj, policy.access_level, tier)


@dataclass
class _Unresolved:
    """A policy tuple read out of a row, before inheritance is applied."""

    access_level: AccessLevel | None
    required_scopes: list[str] | None
    allowed_idps: list[str] | None


def resolve_policy(
    access_level: AccessLevel | None,
    required_scopes: list[str] | None,
    allowed_idps: list[str] | None,
    parent_policy: EffectivePolicy,
) -> EffectivePolicy:
    """The policy for a row holding this tuple, inheriting from ``parent_policy``.

    The same rule as ``get_effective_policy``, over a tuple rather than an
    instance, so an aggregate can resolve a policy without loading the row it
    belongs to. ``parent_policy`` is resolved once by the caller and reused
    across every tuple, so this issues no queries.
    """
    row = _Unresolved(access_level, required_scopes, allowed_idps)
    return _policy_from([row, parent_policy])


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
