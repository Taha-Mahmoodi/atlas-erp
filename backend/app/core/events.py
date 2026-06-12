"""D-011 domain-event bus: collect-then-dispatch, in the SAME transaction.

Three pieces, exactly as D-011 prescribes:

* ``DomainEvent`` — a frozen Pydantic v2 base. Each subclass declares a ClassVar
  ``key`` (module-prefixed past-tense string, e.g. ``'sales.order.shipped'``) and
  carries ``tenant_id`` + ``occurred_at`` plus its own payload fields. Events are
  PLAIN DATA — no behaviour — so a publishing module's ``events.py`` is a sanctioned
  cross-module import (STRUCTURE §5 amendment, D-011): a subscriber in another module's
  ``handlers.py`` imports the typed event class without importing any logic.

* The subscription registry — ``subscribe(key, handler)`` and the ``@on(EventClass)``
  decorator a module's ``handlers.py`` calls at import time; ``clear_subscriptions()``
  / ``subscriptions_snapshot()`` / ``restore_subscriptions()`` give the tests a clean
  registry per case so module-registered handlers in later phases never leak.

* ``InProcessEventBus`` behind the ``EventBus`` Protocol, plus the single shared
  unit-of-work drain point ``run_in_uow``:
  - ``publish(session, event)`` appends to a FIFO buffer in ``session.info`` — NO
    immediate dispatch, so handlers observe the publisher's settled aggregate state.
  - ``run_in_uow(session, work)`` runs the business ``work``, then drains the buffer
    breadth-first (FIFO), invoking each handler with the SAME session so its writes
    land in the SAME transaction, THEN commits. A handler may publish further events;
    those are drained too, up to ``MAX_DISPATCHES_PER_UOW`` total, then ``EventCycleError``.
    ANY exception — business work or any handler — rolls the whole transaction back and
    re-raises: deliberately NO per-handler isolation (if the COGS posting fails, the
    goods issue must not commit). This is the load-bearing all-or-nothing invariant.

**Handler order** is deterministic: per event key, handlers fire in registration order
(module import order in main.py's app factory); events fire in publish (FIFO) order.

**Tenant context** (D-007): handlers run UNDER the trigger's already-active tenant
context, so their tenant-scoped reads/writes are filtered and stamped like any other
write. A handler doing system-level work wraps it in ``system_context()`` itself (the
D-007 site-4 "bus system-event replay" seam) — the bus does not change context for it.

**Audit** (D-010): handler writes share the session, so the before_flush/after_flush
audit listeners capture and tenant-stamp them automatically — no extra wiring (proven
by tests/core/test_events.py).

**Swap path:** the in-transaction semantics ARE the contract, expressed by the
``EventBus`` Protocol. A future ``TransactionalOutboxBus`` implements the same Protocol,
writing ``core_event_outbox`` rows in the same transaction for an external relay, with
zero business-logic changes. The outbox TABLE is introduced THEN (a later PLAN task),
not now — v1 ships only the in-process bus.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AtlasError

# Hard ceiling on handler dispatches per unit of work (D-011): handlers may publish
# further events, drained in the same uow, but a cycle (A -> B -> A) or a runaway fan-out
# would otherwise hold the transaction open forever. At the cap we raise rather than spin.
MAX_DISPATCHES_PER_UOW = 50

# FIFO buffer of not-yet-dispatched events, keyed in session.info so it is per-session
# (per-transaction) and never shared across requests.
_BUFFER_KEY = "pending_events"


class EventCycleError(AtlasError):
    """A unit of work dispatched more than MAX_DISPATCHES_PER_UOW events — almost always
    a handler-publish cycle. Surfaced as a 500 (a server-side wiring fault, not client
    input) and, like every handler failure, rolls the whole transaction back (D-011)."""

    def __init__(self, dispatched: int) -> None:
        super().__init__(
            code="events.cycle_detected",
            message=(
                f"Event dispatch exceeded the per-transaction cap of "
                f"{MAX_DISPATCHES_PER_UOW} (dispatched {dispatched}); likely a handler "
                "publish cycle."
            ),
            status_code=500,
        )


class DomainEvent(BaseModel):
    """Base for every domain event (D-011). Frozen + plain data, no behaviour.

    Subclasses declare their string key and payload:

        class SalesOrderShipped(DomainEvent):
            key: ClassVar[str] = "sales.order.shipped"
            order_id: uuid.UUID

    ``key`` is a ClassVar (one value per event TYPE, not a per-instance field) so it is
    not part of the payload schema; ``tenant_id`` + ``occurred_at`` are carried on every
    event. ``frozen=True`` makes instances immutable — an event is a fact that happened.
    """

    model_config = ConfigDict(frozen=True)

    # Declared on the base as a sentinel; every concrete subclass overrides it. Kept as a
    # ClassVar so Pydantic does not treat it as a payload field.
    key: ClassVar[str] = ""

    tenant_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# A handler is an async callable taking the shared session and the event, returning None.
# It runs before commit, inside the trigger's transaction and tenant context (D-011/D-007).
Handler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]

# Registry: event key -> handlers in registration order. Module import order (main.py's
# app factory) therefore fixes handler order deterministically (D-011).
_subscriptions: dict[str, list[Handler]] = {}


def subscribe(event_key: str, handler: Handler) -> None:
    """Register ``handler`` for ``event_key``. Called by a module's handlers.py at import,
    directly or via the ``@on`` decorator. Order of registration = dispatch order."""
    _subscriptions.setdefault(event_key, []).append(handler)


def on(event_type: type[DomainEvent]) -> Callable[[Handler], Handler]:
    """Decorator form of subscribe, keyed off the event CLASS so handlers.py stays typed:

        @on(SalesOrderShipped)
        async def post_cogs(session: AsyncSession, event: SalesOrderShipped) -> None: ...

    Returns the handler unchanged so it can still be called/tested directly."""

    def decorator(handler: Handler) -> Handler:
        subscribe(event_type.key, handler)
        return handler

    return decorator


def handlers_for(event_key: str) -> tuple[Handler, ...]:
    """Registered handlers for a key, in registration order (empty tuple if none)."""
    return tuple(_subscriptions.get(event_key, ()))


def clear_subscriptions() -> None:
    """Drop every registration. The autouse test fixture calls this so handlers a module
    registers at import in later phases cannot leak between tests (D-025 isolation)."""
    _subscriptions.clear()


def subscriptions_snapshot() -> dict[str, list[Handler]]:
    """Deep-ish copy of the registry for save/restore around a test that mutates it."""
    return {key: list(value) for key, value in _subscriptions.items()}


def restore_subscriptions(snapshot: dict[str, list[Handler]]) -> None:
    """Replace the registry with a previously taken snapshot."""
    _subscriptions.clear()
    _subscriptions.update({key: list(value) for key, value in snapshot.items()})


def _buffer(session: AsyncSession) -> list[DomainEvent]:
    return session.info.setdefault(_BUFFER_KEY, [])


@runtime_checkable
class EventBus(Protocol):
    """The swappable contract (D-011). The in-transaction semantics live in ``run_in_uow``,
    not here, so any implementation (in-process now, a transactional-outbox bus later)
    publishes the same way and business logic never changes. ``publish`` buffers; it does
    NOT dispatch — dispatch is owned by the single ``run_in_uow`` drain point."""

    def publish(self, session: AsyncSession, event: DomainEvent) -> None: ...


class InProcessEventBus:
    """The only EventBus implementation in v1 (D-011). ``publish`` appends to the per-session
    FIFO buffer; the buffer is drained by ``run_in_uow`` after the business work and before
    commit, so handlers run synchronously in the trigger's transaction."""

    def publish(self, session: AsyncSession, event: DomainEvent) -> None:
        _buffer(session).append(event)


# Module-level singleton: services import this and call ``bus.publish(session, event)``.
# A later outbox bus replaces THIS binding (same Protocol) and nothing else moves.
bus: EventBus = InProcessEventBus()


def publish(session: AsyncSession, event: DomainEvent) -> None:
    """Convenience free function delegating to the active bus, so callers can
    ``from app.core.events import publish`` without reaching for the singleton."""
    bus.publish(session, event)


async def _drain_and_dispatch(session: AsyncSession) -> None:
    """Pop buffered events FIFO and run their handlers, sharing ``session``. Handlers may
    publish more events (appended to the same buffer); we keep draining breadth-first up to
    MAX_DISPATCHES_PER_UOW total dispatches, then raise EventCycleError. A handler raising
    propagates — run_in_uow's caller rolls the whole transaction back (D-011: no isolation).
    """
    buffer = _buffer(session)
    dispatched = 0
    while buffer:
        event = buffer.pop(0)  # FIFO: oldest first
        for handler in handlers_for(event.key):
            if dispatched >= MAX_DISPATCHES_PER_UOW:
                raise EventCycleError(dispatched)
            await handler(session, event)
            dispatched += 1
    # Defensive: an event with no handler still counts toward nothing; a cap breach can
    # only happen above. Clearing the (now empty) key keeps session.info tidy.
    session.info.pop(_BUFFER_KEY, None)


async def run_in_uow(
    session: AsyncSession,
    work: Callable[[], Awaitable[None]] | Awaitable[None],
) -> None:
    """The single sanctioned unit-of-work helper (D-011). Used by the request session
    dependency (core/deps), by seed.py and by CLI flows, so HTTP, seed and tests get
    IDENTICAL event semantics.

    Sequence: run ``work`` (the business mutation that publishes events) -> drain the
    buffered events FIFO and run their handlers on the SAME session (so handler effects,
    e.g. a COGS journal, are in the same transaction as the trigger, e.g. the stock
    issue) -> commit. If the business work OR any handler raises (or the cascade cap is
    hit), roll the WHOLE transaction back and re-raise — the trigger's own writes do not
    persist. Handlers run under the trigger's active tenant context (D-007); nothing here
    changes it.

    ``work`` may be a coroutine object or a zero-arg callable returning an awaitable, so
    both ``run_in_uow(session, service_coro)`` and ``run_in_uow(session, lambda: ...)``
    read naturally at call sites.
    """
    try:
        awaitable = work() if callable(work) else work
        await awaitable
        await _drain_and_dispatch(session)
        await session.commit()
    except Exception:
        await session.rollback()
        # Drop any partially drained / leftover buffer so the next uow on this session
        # (tests reuse one session) starts clean.
        session.info.pop(_BUFFER_KEY, None)
        raise
