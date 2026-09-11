from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum

from app.models.identity import AuthenticatedUser

# List endpoints accept an unbounded `limit`, so the arrays need their own cap.
MAX_RECORDED_PER_TIER = 1000


class ReadTier(StrEnum):
    """How closely a caller looked at a resource."""

    LISTED = "listed"
    READ = "read"


@dataclass
class RequestContext:
    """Mutable state shared between the middleware and the code it wraps."""

    actor: AuthenticatedUser | None = None
    restricted: dict[ReadTier, dict[str, set[int]]] = field(
        default_factory=lambda: {tier: {} for tier in ReadTier}
    )
    truncated: bool = False
    returned: int = 0


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "fds_request_context", default=None
)


@contextmanager
def request_context() -> Generator[RequestContext]:
    """Install a fresh context for the duration of one request."""
    ctx = RequestContext()
    token = _request_context.set(ctx)
    try:
        yield ctx
    finally:
        _request_context.reset(token)


def get_request_context() -> RequestContext | None:
    """The current context, or None outside a request."""
    return _request_context.get()


def set_actor(user: AuthenticatedUser) -> None:
    """Record who is making this request."""
    ctx = _request_context.get()
    if ctx is not None:
        ctx.actor = user


def get_actor() -> AuthenticatedUser | None:
    """The authenticated user for this request, or None outside a request."""
    ctx = _request_context.get()
    return ctx.actor if ctx is not None else None


def record_returned(count: int) -> None:
    """Add to the number of items this request has served from list endpoints."""
    ctx = _request_context.get()
    if ctx is not None:
        ctx.returned += count


def record_restricted_access(
    resource_type: str, resource_id: int, tier: ReadTier
) -> None:
    """Record that the caller was served a resource that is not public."""
    ctx = _request_context.get()
    if ctx is None:
        return

    by_type = ctx.restricted[tier]
    if sum(len(ids) for ids in by_type.values()) >= MAX_RECORDED_PER_TIER:
        ctx.truncated = True
        return
    by_type.setdefault(resource_type, set()).add(resource_id)


def drain_restricted_access() -> dict[str, dict[str, list[int]]]:
    """Return what was accessed, keyed for the audit line, and clear it."""
    ctx = _request_context.get()
    if ctx is None:
        return {}

    drained = {
        f"restricted_{tier.value}": {
            resource_type: sorted(ids) for resource_type, ids in by_type.items() if ids
        }
        for tier, by_type in ctx.restricted.items()
    }
    for by_type in ctx.restricted.values():
        by_type.clear()
    return {key: value for key, value in drained.items() if value}
