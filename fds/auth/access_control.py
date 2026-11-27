from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, col, or_, select, tuple_

from fds.auth.permissions import (
    check_is_admin,
    check_sets_write_roles,
    check_write_roles,
    holds_any,
    role_refusal,
)
from fds.core.audit import record_restricted_read
from fds.core.config import config
from fds.core.context import ReadTier
from fds.models.collection import Collection
from fds.models.dataset import Dataset
from fds.models.device import Device
from fds.models.identity import AuthenticatedUser
from fds.models.policy import AccessLevel
from fds.models.shot import Shot
from fds.models.source import Source
from fds.services.exceptions import FDSValidationError, ForbiddenError

DEFAULT_ACCESS_LEVEL = AccessLevel.RESTRICTED


@dataclass
class EffectivePolicy:
    """
    Resolved authorization policy for a record, after walking the
    Dataset/Collection → Shot → Device or Source → Device inheritance chain.

    access_level:   The effective visibility / auth baseline.
    read_roles and write_roles:
        None  → no roles named; only fds-admin, or a writer for reads.
        []    → anyone signed in from an allowed IdP.
        [..] → any one of the listed roles.
    allowed_idps:
        None  → any issuer that is globally trusted is accepted.
        [..] → user's issuer must appear in this list (subset of TRUSTED_IDPS).
    """

    access_level: AccessLevel
    read_roles: list[str] | None
    write_roles: list[str] | None
    allowed_idps: list[str] | None


Policied = Collection | Dataset | Shot | Device | Source

# The fields that inherit. Each resolves independently: a Shot may set
# access_level while read_roles still comes from its Device.
_POLICY_FIELDS = ("access_level", "read_roles", "write_roles", "allowed_idps")


def _parents(
    records: Sequence[Policied], session: Session
) -> tuple[dict[tuple[str, str], Shot], dict[str | int, Device]]:
    """The shots and devices ``records`` inherit policy from, a query each.

    Devices are keyed by name, and by id for the Sources that link to them.
    """
    # A record that sets every policy field inherits nothing, so there is no
    # chain worth loading.
    inheriting = [
        r for r in records if any(getattr(r, f, None) is None for f in _POLICY_FIELDS)
    ]
    shot_keys = {
        (r.device_name, r.shot_id)
        for r in inheriting
        if isinstance(r, (Dataset, Collection)) and r.shot_id and r.device_name
    }
    names = {name for r in inheriting if (name := getattr(r, "device_name", None))}
    ids = {r.device_id for r in inheriting if isinstance(r, Source) and r.device_id}

    shots = (
        session.exec(
            select(Shot).where(
                tuple_(col(Shot.device_name), col(Shot.id)).in_(shot_keys)
            )
        ).all()
        if shot_keys
        else []
    )
    devices = (
        session.exec(
            select(Device).where(
                or_(col(Device.name).in_(names), col(Device.id).in_(ids))
            )
        ).all()
        if names or ids
        else []
    )
    by_key: dict[str | int, Device] = {d.name: d for d in devices}
    by_key |= {d.id: d for d in devices if d.id is not None}
    return {(s.device_name, s.id): s for s in shots}, by_key


def _chain(
    obj: Policied,
    shots: dict[tuple[str, str], Shot],
    devices: dict[str | int, Device],
) -> list[Policied]:
    """``obj`` and the objects it inherits policy from, nearest first.

    Collection/Dataset → Shot → Device, and Source → Device. A Collection or
    Dataset not attached to a shot inherits from its device directly, a Source
    linked to no device inherits from nothing, and a Device inherits from
    nothing because it has no ``device_name`` of its own.
    """
    chain: list[Policied] = [obj]

    if isinstance(obj, (Dataset, Collection)) and obj.shot_id and obj.device_name:
        shot = shots.get((obj.device_name, obj.shot_id))
        if shot:
            chain.append(shot)

    device_key = (
        obj.device_id if isinstance(obj, Source) else getattr(obj, "device_name", None)
    )
    if device_key:
        device = devices.get(device_key)
        if device:
            chain.append(device)

    return chain


def _inherit(sources: Sequence[Any], field: str) -> Any:
    """The first explicitly-set value of ``field`` along ``sources``.

    ``None`` means "not set, keep looking"; every other value stops the walk,
    including an empty ``read_roles``, which is a policy in its own right
    (any authenticated user from an allowed IdP) rather than an absence.
    """
    for source in sources:
        value = getattr(source, field, None)
        if value is not None:
            return value
    return None


def _policy_from(sources: Sequence[Any]) -> EffectivePolicy:
    """Resolve every policy field over one ordered list of policy sources."""
    access_level, read_roles, write_roles, allowed_idps = (
        _inherit(sources, field) for field in _POLICY_FIELDS
    )
    return EffectivePolicy(
        access_level=access_level or DEFAULT_ACCESS_LEVEL,
        read_roles=read_roles,
        write_roles=write_roles,
        allowed_idps=allowed_idps,
    )


def get_effective_policies(
    records: Sequence[Policied], session: Session
) -> list[EffectivePolicy]:
    """The policy that applies to each of ``records``, after inheritance.

    Specific overrides general: the nearest explicitly-set value for each field
    wins, and an unset ``access_level`` anywhere in the chain falls back to
    ``DEFAULT_ACCESS_LEVEL``. However many records there are, the shots and
    devices they inherit from load in a query each.
    """
    shots, devices = _parents(records, session)
    return [_policy_from(_chain(r, shots, devices)) for r in records]


def get_effective_policy(obj: Policied, session: Session) -> EffectivePolicy:
    """The policy that applies to ``obj``, after inheritance."""
    return get_effective_policies([obj], session)[0]


def get_effective_access_level(obj: Policied, session: Session) -> AccessLevel:
    """The effective access level for ``obj``, for callers wanting only that."""
    return get_effective_policy(obj, session).access_level


# A policy with nothing above it, so every unset field falls to the default.
NO_PARENT = EffectivePolicy(
    access_level=DEFAULT_ACCESS_LEVEL,
    read_roles=None,
    write_roles=None,
    allowed_idps=None,
)


def holds_read_roles(user: AuthenticatedUser, policy: EffectivePolicy) -> bool:
    """Whether ``user`` holds a role that reads a record under ``policy``.

    A role that writes the record reads it too.
    """
    return holds_any(user, policy.read_roles) or holds_any(user, policy.write_roles)


def read_denial(
    kind: type[Policied], policy: EffectivePolicy, user: AuthenticatedUser
) -> str | None:
    """Why ``user`` may not read a ``kind`` record's metadata, or ``None`` if they may.

    Credentials for the record's data are decided separately, at vending.
    """
    if user.is_admin():
        return None
    if policy.access_level in (AccessLevel.PUBLIC, AccessLevel.EMBARGOED):
        return None
    if user.is_anonymous:
        return "Authentication required for this resource"
    if policy.allowed_idps is not None and user.issuer not in policy.allowed_idps:
        return (
            "Access denied: your identity provider is not permitted for this resource"
        )
    if holds_read_roles(user, policy):
        return None
    if policy.read_roles is None and kind in (Device, Shot):
        return None
    return str(role_refusal([*(policy.read_roles or []), *(policy.write_roles or [])]))


def check_write(obj: Policied, session: Session, user: AuthenticatedUser) -> None:
    """Enforce write access to ``obj``: changing it, deleting it, or adding to it."""
    check_write_roles(user, get_effective_policy(obj, session).write_roles)


def check_create(
    session: Session,
    user: AuthenticatedUser,
    device_name: str | None,
    shot_id: str | None = None,
) -> None:
    """Enforce that ``user`` may create a record on a device, or in one of its shots.

    A record on no device has no parent to name write roles, so it needs
    ``fds-admin``. So does one on a device or shot that does not exist, which
    leaves only ``fds-admin`` to reach the caller's not-found error.
    """
    parent: Policied | None = None
    if device_name is not None and shot_id is not None:
        parent = session.exec(
            select(Shot).where(Shot.device_name == device_name, Shot.id == shot_id)
        ).first()
    elif device_name is not None:
        parent = session.exec(select(Device).where(Device.name == device_name)).first()
    if parent is None:
        check_is_admin(user)
    else:
        check_write(parent, session, user)


def check_activity_write(
    session: Session, user: AuthenticatedUser, activity_id: int
) -> None:
    """Enforce write access to an Activity, which carries no write roles of its own.

    The caller needs write access to every Dataset the Activity generated and
    every Collection that bundles it. An Activity with neither needs ``fds-admin``.
    """
    if user.is_admin():
        return
    records: list[Policied] = [
        *session.exec(select(Dataset).where(Dataset.activity_id == activity_id)),
        *session.exec(select(Collection).where(Collection.activity_id == activity_id)),
    ]
    if not records:
        check_is_admin(user)
    for policy in get_effective_policies(records, session):
        check_write_roles(user, policy.write_roles)


def check_activity_change(
    session: Session, user: AuthenticatedUser, current: int | None, wanted: int | None
) -> None:
    """Enforce write access to each Activity a record's ``activity_id`` moves between.

    Moving a record to or from an Activity changes that Activity.
    """
    if wanted == current:
        return
    for activity_id in (current, wanted):
        if activity_id is not None:
            check_activity_write(session, user, activity_id)


def check_policy_update(
    user: AuthenticatedUser, record: Policied, changes: dict[str, Any]
) -> None:
    """Check the policy fields an update to ``record`` sends in ``changes``.

    Only ``fds-admin`` changes its write roles, and its issuer list must be valid.
    """
    check_sets_write_roles(
        user, changes.get("write_roles", record.write_roles), record.write_roles
    )
    validate_allowed_idps(changes.get("allowed_idps", record.allowed_idps))


def check_read(
    obj: Policied,
    session: Session,
    user: AuthenticatedUser,
    tier: ReadTier = ReadTier.READ,
) -> None:
    """Enforce read access to ``obj``, and record it when it is restricted."""
    check_read_with_policy(obj, get_effective_policy(obj, session), user, tier)


def check_read_with_policy(
    obj: Policied,
    policy: EffectivePolicy,
    user: AuthenticatedUser,
    tier: ReadTier,
) -> None:
    """``check_read`` for a caller that has already resolved ``obj``'s policy.

    Resolving a list's policies together and checking each record with this is
    how a list avoids a policy lookup per record.
    """
    denial = read_denial(type(obj), policy, user)
    if denial:
        raise ForbiddenError(denial)
    record_restricted_read(obj, policy.access_level, tier)


@dataclass
class _Unresolved:
    """A policy tuple read out of a row, before inheritance is applied."""

    access_level: AccessLevel | None
    read_roles: list[str] | None
    write_roles: list[str] | None
    allowed_idps: list[str] | None


def resolve_policy(
    access_level: AccessLevel | None,
    read_roles: list[str] | None,
    write_roles: list[str] | None,
    allowed_idps: list[str] | None,
    parent_policy: EffectivePolicy,
) -> EffectivePolicy:
    """The policy for a row holding this tuple, inheriting from ``parent_policy``.

    The same rule as ``get_effective_policy``, over a tuple rather than an
    instance, so an aggregate can resolve a policy without loading the row it
    belongs to. ``parent_policy`` is resolved once by the caller and reused
    across every tuple, so this issues no queries.
    """
    row = _Unresolved(access_level, read_roles, write_roles, allowed_idps)
    return _policy_from([row, parent_policy])


def validate_allowed_idps(allowed_idps: list[str] | None) -> None:
    """
    Validates a record's allowed_idps before a Device, Shot, Collection,
    Dataset or Source is written.

    The list may be set at any access level, as read_roles and write_roles
    may: it applies wherever the effective level restricts, on the record or
    on the records that inherit from it. When set, it must be non-empty and
    every entry must match an issuer in the globally-configured TRUSTED_IDPS,
    so TRUSTED_IDPS must not be empty.
    """
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
