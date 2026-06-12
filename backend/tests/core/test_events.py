"""D-011 domain-event bus, proven against the real session/db on the migrated template.

Covers: publish buffers (no dispatch until run_in_uow drains); handlers run before commit
sharing the session; deterministic FIFO/registration ordering; the cardinal atomicity
invariant (a handler failure rolls the trigger's own write back); cascade draining + the
recursion cap; handler writes are audited and tenant-stamped automatically; subscription
isolation; and the swappable Protocol surface.

Self-contained per D-011 item 3: tests define LOCAL DomainEvent subclasses + handlers and
exercise the bus against the real db. Where a handler effect must be proven to persist (or
roll back) in the trigger's transaction, an existing audited tenant-scoped model
(adm_tenant_settings) stands in for a business row — no fake business module is invented.
"""

import uuid
from typing import ClassVar

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    MAX_DISPATCHES_PER_UOW,
    DomainEvent,
    EventBus,
    EventCycleError,
    InProcessEventBus,
    bus,
    handlers_for,
    on,
    publish,
    run_in_uow,
    subscribe,
)
from app.core.models import AuditLog
from app.core.tenancy import tenant_context
from app.modules.admin.models import TenantSetting

# --- Local event definitions (plain data, declarative — D-011 item 3) ----------


class StockIssued(DomainEvent):
    """Stand-in trigger event: 'inventory issued stock for a sale'."""

    key: ClassVar[str] = "test.stock.issued"
    move_ref: str


class OrderConfirmed(DomainEvent):
    key: ClassVar[str] = "test.order.confirmed"
    order_ref: str


async def _setting_count(session: AsyncSession, tenant_id: uuid.UUID, key: str) -> int:
    """Count TenantSetting rows for a key under the tenant's own (filtered) context."""
    with tenant_context(tenant_id):
        stmt = select(func.count()).select_from(TenantSetting).where(TenantSetting.key == key)
        return (await session.execute(stmt)).scalar_one()


# --- publish buffers; no dispatch until run_in_uow drains ----------------------


async def test_publish_buffers_and_does_not_dispatch_until_uow_drains(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    fired: list[str] = []

    @on(StockIssued)
    async def record(session: AsyncSession, event: StockIssued) -> None:
        fired.append(event.move_ref)

    with tenant_context(tenant_a):
        publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="M1"))
        # Buffered only: the handler has NOT run yet.
        assert fired == []
        assert db_session.info["pending_events"]

        async def work() -> None:
            return None

        await run_in_uow(db_session, work)

    # run_in_uow drained the buffer and ran the handler exactly once.
    assert fired == ["M1"]


# --- handler runs before commit, sharing the session ---------------------------


async def test_handler_runs_before_commit_and_shares_session(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    seen_in_handler: list[int] = []

    @on(StockIssued)
    async def cogs_handler(session: AsyncSession, event: StockIssued) -> None:
        # The trigger's write is already visible on the SHARED session before commit.
        seen_in_handler.append(await _setting_count(session, tenant_a, "trigger"))
        session.add(TenantSetting(tenant_id=tenant_a, key="cogs", value={"ref": event.move_ref}))

    with tenant_context(tenant_a):

        async def work() -> None:
            db_session.add(TenantSetting(tenant_id=tenant_a, key="trigger", value={"ref": "M1"}))
            publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="M1"))

        await run_in_uow(db_session, work)

    # Handler saw the trigger row before commit (shared session, same transaction)...
    assert seen_in_handler == [1]
    # ...and both rows committed together.
    assert await _setting_count(db_session, tenant_a, "trigger") == 1
    assert await _setting_count(db_session, tenant_a, "cogs") == 1


# --- FIFO ordering of events and registration ordering of handlers -------------


async def test_events_dispatch_fifo_and_handlers_in_registration_order(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    order: list[str] = []

    # Two handlers for ONE event key: they must fire in registration order.
    @on(OrderConfirmed)
    async def first(session: AsyncSession, event: OrderConfirmed) -> None:
        order.append(f"{event.order_ref}:h1")

    @on(OrderConfirmed)
    async def second(session: AsyncSession, event: OrderConfirmed) -> None:
        order.append(f"{event.order_ref}:h2")

    with tenant_context(tenant_a):

        async def work() -> None:
            # Two events: must drain oldest-first (FIFO).
            publish(db_session, OrderConfirmed(tenant_id=tenant_a, order_ref="A"))
            publish(db_session, OrderConfirmed(tenant_id=tenant_a, order_ref="B"))

        await run_in_uow(db_session, work)

    # Event A fully (both handlers, in order) before event B — events FIFO, handlers in
    # registration order. This is the documented deterministic guarantee (D-011).
    assert order == ["A:h1", "A:h2", "B:h1", "B:h2"]


# --- THE cardinal D-011 invariant: handler failure rolls the trigger back ------


async def test_handler_failure_rolls_back_trigger_write(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Stock issue + COGS handler fails -> the stock issue must NOT commit. We assert the
    trigger row count is 0 after the rollback — the all-or-nothing invariant, unambiguous."""

    class CogsPostingError(RuntimeError):
        pass

    @on(StockIssued)
    async def failing_cogs(session: AsyncSession, event: StockIssued) -> None:
        # Even writes its own row first, to prove the handler's partial effect is discarded.
        session.add(TenantSetting(tenant_id=tenant_a, key="cogs", value={}))
        raise CogsPostingError("COGS posting failed")

    with tenant_context(tenant_a):

        async def work() -> None:
            db_session.add(TenantSetting(tenant_id=tenant_a, key="stock", value={"ref": "M1"}))
            publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="M1"))

        with pytest.raises(CogsPostingError):
            await run_in_uow(db_session, work)

    # The trigger's OWN write rolled back with the failing handler — both counts are 0.
    assert await _setting_count(db_session, tenant_a, "stock") == 0
    assert await _setting_count(db_session, tenant_a, "cogs") == 0


async def test_business_work_failure_rolls_back_and_skips_handlers(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    fired: list[str] = []

    @on(StockIssued)
    async def handler(session: AsyncSession, event: StockIssued) -> None:
        fired.append(event.move_ref)

    with tenant_context(tenant_a):

        async def work() -> None:
            db_session.add(TenantSetting(tenant_id=tenant_a, key="stock", value={}))
            publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="M1"))
            raise RuntimeError("business rule violated after publish")

        with pytest.raises(RuntimeError):
            await run_in_uow(db_session, work)

    # Work failed before the drain: handlers never ran and nothing committed.
    assert fired == []
    assert await _setting_count(db_session, tenant_a, "stock") == 0


# --- cascade: a handler that publishes another event is drained in the same uow -


async def test_handler_published_event_is_drained_in_same_uow(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    chain: list[str] = []

    @on(OrderConfirmed)
    async def on_order(session: AsyncSession, event: OrderConfirmed) -> None:
        chain.append("order")
        # A handler publishes a downstream event — must be drained in THIS uow.
        publish(session, StockIssued(tenant_id=event.tenant_id, move_ref="from-order"))

    @on(StockIssued)
    async def on_stock(session: AsyncSession, event: StockIssued) -> None:
        chain.append(f"stock:{event.move_ref}")

    with tenant_context(tenant_a):

        async def work() -> None:
            publish(db_session, OrderConfirmed(tenant_id=tenant_a, order_ref="A"))

        await run_in_uow(db_session, work)

    assert chain == ["order", "stock:from-order"]


async def test_cascade_cap_raises_event_cycle_error(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A deliberate cycle (the handler re-publishes the same event) must hit the cap and
    raise EventCycleError rather than spin forever — and roll the transaction back."""
    dispatches: list[int] = []

    @on(StockIssued)
    async def loops(session: AsyncSession, event: StockIssued) -> None:
        dispatches.append(1)
        publish(session, StockIssued(tenant_id=event.tenant_id, move_ref="loop"))

    with tenant_context(tenant_a):

        async def work() -> None:
            publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="seed"))

        with pytest.raises(EventCycleError) as excinfo:
            await run_in_uow(db_session, work)

    assert excinfo.value.code == "events.cycle_detected"
    assert excinfo.value.status_code == 500
    # The cap bounded the runaway: exactly MAX_DISPATCHES_PER_UOW handlers ran, no more.
    assert len(dispatches) == MAX_DISPATCHES_PER_UOW


# --- handler writes are audited + tenant-stamped (item 2, proven not reimplemented) -


async def test_handler_write_is_audited_and_tenant_stamped(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A handler inserts an audited row; because it shares the session and runs before
    commit, the D-010 flush listeners capture it and the D-007 stamp sets tenant_id —
    no extra wiring. We prove the audit row exists and is stamped with the trigger tenant."""

    @on(StockIssued)
    async def writes_audited_row(session: AsyncSession, event: StockIssued) -> None:
        # tenant_id left unset on purpose: the before_flush stamp must fill it from context.
        session.add(TenantSetting(key="handler-write", value={"ref": event.move_ref}))

    with tenant_context(tenant_a):

        async def work() -> None:
            publish(db_session, StockIssued(tenant_id=tenant_a, move_ref="M1"))

        await run_in_uow(db_session, work)

    with tenant_context(tenant_a):
        setting = (
            await db_session.execute(
                select(TenantSetting).where(TenantSetting.key == "handler-write")
            )
        ).scalar_one()
        audit_rows = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity_table == "adm_tenant_settings",
                    AuditLog.entity_id == str(setting.id),
                    AuditLog.action == "INSERT",
                )
            )
        ).scalars().all()

    # The handler's write was tenant-stamped from context...
    assert setting.tenant_id == tenant_a
    # ...and audited in the same transaction, stamped to the same tenant.
    assert len(audit_rows) == 1
    assert audit_rows[0].tenant_id == tenant_a


# --- subscription isolation (the autouse clear_event_subscriptions fixture) -----


async def test_subscriptions_are_empty_at_test_start() -> None:
    """The autouse fixture resets the registry, so each test starts with no handlers —
    handlers registered by other tests (or later-phase module handlers.py) cannot leak."""
    assert handlers_for(StockIssued.key) == ()
    assert handlers_for(OrderConfirmed.key) == ()


async def test_subscribe_registers_handler_for_its_key() -> None:
    async def handler(session: AsyncSession, event: DomainEvent) -> None:
        return None

    subscribe(StockIssued.key, handler)
    assert handlers_for(StockIssued.key) == (handler,)
    # A different key is unaffected — registration is per key.
    assert handlers_for(OrderConfirmed.key) == ()


# --- swappable Protocol surface (light sanity) ---------------------------------


def test_in_process_bus_satisfies_event_bus_protocol() -> None:
    """The bus is consumed via the EventBus Protocol so a future outbox bus can replace it
    without touching business logic (D-011 swap path). Light check of the public surface."""
    assert isinstance(bus, EventBus)
    assert isinstance(InProcessEventBus(), EventBus)
    # publish is the Protocol's single method; run_in_uow is the separate drain seam.
    assert hasattr(bus, "publish")
