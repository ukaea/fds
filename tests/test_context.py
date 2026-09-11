from contextvars import ContextVar

from starlette.concurrency import run_in_threadpool

from app.core.context import (
    MAX_RECORDED_PER_TIER,
    ReadTier,
    drain_restricted_access,
    get_actor,
    record_restricted_access,
    request_context,
    set_actor,
)
from app.models.identity import ANONYMOUS_USER


async def test_mutation_from_worker_thread_is_visible_to_caller():
    """The property the whole design rests on."""

    def handler() -> None:
        record_restricted_access("dataset", 1183, ReadTier.READ)

    with request_context():
        await run_in_threadpool(handler)

        assert drain_restricted_access() == {"restricted_read": {"dataset": [1183]}}


async def test_rebinding_from_worker_thread_is_lost():
    """Why the module does not simply call ContextVar.set().

    This is the behaviour that makes the obvious simplification wrong. If this
    test ever fails, Python's context semantics have changed and the warnings
    in app/core/context.py can be revisited.
    """
    var: ContextVar[str] = ContextVar("probe", default="unset")
    var.set("from-caller")

    def handler() -> None:
        var.set("from-worker")

    await run_in_threadpool(handler)

    assert var.get() == "from-caller"


async def test_actor_set_from_worker_thread_is_visible():
    """Guards a change of get_current_user from `async def` to `def`."""
    with request_context():
        await run_in_threadpool(lambda: set_actor(ANONYMOUS_USER))

        actor = get_actor()
        assert actor is not None
        assert actor.id == "anonymous"


class TestOutsideARequest:
    """The demo script calls services directly, with no request in flight."""

    def test_accessors_are_inert(self):
        record_restricted_access("dataset", 1, ReadTier.READ)
        set_actor(ANONYMOUS_USER)

        assert get_actor() is None
        assert drain_restricted_access() == {}


class TestAccumulator:
    def test_ids_are_deduplicated_and_sorted(self):
        with request_context():
            for dataset_id in (9, 3, 9, 1):
                record_restricted_access("dataset", dataset_id, ReadTier.LISTED)

            assert drain_restricted_access() == {
                "restricted_listed": {"dataset": [1, 3, 9]}
            }

    def test_tiers_are_kept_apart(self):
        with request_context():
            record_restricted_access("dataset", 1, ReadTier.LISTED)
            record_restricted_access("shot", 2, ReadTier.READ)

            assert drain_restricted_access() == {
                "restricted_listed": {"dataset": [1]},
                "restricted_read": {"shot": [2]},
            }

    def test_draining_clears(self):
        with request_context():
            record_restricted_access("dataset", 1, ReadTier.READ)

            assert drain_restricted_access()
            assert drain_restricted_access() == {}

    def test_recording_is_capped(self):
        """List endpoints take an unbounded `limit`, so this has to be bounded."""
        with request_context() as context:
            for dataset_id in range(MAX_RECORDED_PER_TIER + 50):
                record_restricted_access("dataset", dataset_id, ReadTier.LISTED)

            assert context.truncated is True
            recorded = drain_restricted_access()["restricted_listed"]["dataset"]
            assert len(recorded) == MAX_RECORDED_PER_TIER


def test_context_does_not_leak_between_requests():
    """Two callers in one thread must not see each other's state."""
    with request_context():
        record_restricted_access("dataset", 1, ReadTier.READ)

    with request_context():
        assert drain_restricted_access() == {}
