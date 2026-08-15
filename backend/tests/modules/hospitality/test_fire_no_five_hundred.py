"""Adversarial, end to end: can a real ticket put a guest in front of an HTTP 500?

``test_depletion_dispatch_ceiling.py`` measures the dispatch cost at the service layer. This file
drives the same worst shapes through the REAL staff endpoint and the REAL job runner, because that
is where Q4's failure actually lands — ``EventCycleError`` is a 500, and the ticket the server is
holding is a table waiting to eat.

Two things it attacks that a service-level test cannot:

* the FIRE response status for a 56-line, no-sharing check (aggregation collapses nothing there);
* the concurrency the chunker BUYS. Splitting a huge aggregate is what keeps each uow under the cap,
  but ``MAX_CONCURRENT_JOBS = 4`` then runs those chunks at the same time against the same bin and
  the same ``inv_stock_moves`` number sequence — a lock the D-012 gapless claim holds to commit. A
  ticket wide enough to need three chunks must still deplete completely.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import build_session_factory
from app.core.events import run_in_uow
from app.core.jobs import Job, JobStatus, schedule_job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.main import register_event_handlers
from app.modules.hospitality.constants import DEPLETE_TICKET_JOB
from app.modules.hospitality.service import depletion, tickets
from app.modules.inventory import queries as inventory_queries
from tests.modules.hospitality.conftest import HospitalityApi
from tests.modules.hospitality.factories import build_dish, build_kitchen, build_open_ticket
from tests.modules.inventory.factories import StockSetup, build_item, build_stock


@pytest.fixture
def job_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return build_session_factory(db_engine)


async def _wide_menu(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    setup: StockSetup,
    *,
    dishes: int,
    per_dish: int,
    prefix: str,
) -> list[uuid.UUID]:
    """``dishes`` dishes of ``per_dish`` ingredients each, sharing NOTHING — the shape aggregation
    is powerless against. Everything is stocked, so the only thing that can fail is the bus."""
    dish_ids: list[uuid.UUID] = []
    for index in range(dishes):
        recipe: dict[uuid.UUID, Decimal] = {}
        for slot in range(per_dish):
            item = await build_item(
                session,
                tenant_id,
                item_code=f"{prefix}-I-{index:02d}-{slot:02d}",
                category_id=setup.category_id,
                base_uom_id=setup.base_uom_id,
                name=f"{prefix} ingredient {index}/{slot}",
            )
            await build_stock(session, tenant_id, item.id, setup.bin_a_id, Decimal(500))
            recipe[item.id] = Decimal(1)
        dish_ids.append(
            await build_dish(
                session, tenant_id, setup, item_code=f"{prefix}-D-{index:02d}", recipe=recipe
            )
        )
    return dish_ids


async def _jobs(session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    session.expire_all()
    with tenant_context(tenant_id):
        rows = await session.execute(
            select(Job).where(Job.job_type == DEPLETE_TICKET_JOB).order_by(Job.created_at)
        )
        return list(rows.scalars().all())


async def test_firing_a_fifty_six_line_check_returns_200_not_500(
    hospitality_api: HospitalityApi, db_session: AsyncSession
) -> None:
    """Q4's 8-top, with the shared mirepoix taken away so aggregation cannot save it: 8 dishes at 7
    DISJOINT ingredients is 56 issue lines against a cap of 50. The server presses fire; the guest
    must not be looking at a 500."""
    dish_ids = await _wide_menu(
        db_session,
        hospitality_api.tenant_id,
        hospitality_api.kitchen.setup,
        dishes=8,
        per_dish=7,
        prefix="EIGHTTOP",
    )
    client: AsyncClient = hospitality_api.client
    opened = await client.post(
        "/api/v1/hospitality/tickets",
        headers={"Idempotency-Key": uuid.uuid4().hex},
        json={
            "table_code": "T12",
            "guest_count": 8,
            "lines": [
                {"item_id": str(dish_id), "quantity": "1", "unit_price": "24.00"}
                for dish_id in dish_ids
            ],
        },
    )
    assert opened.status_code == 201, opened.text

    fired = await client.post(
        f"/api/v1/hospitality/tickets/{opened.json()['id']}/fire",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert fired.status_code == 200, fired.text
    assert fired.json()["status"] == "SENT_TO_KITCHEN"

    await wait_for_jobs()
    jobs = await _jobs(db_session, hospitality_api.tenant_id)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value] * 2, (
        f"the depletion failed: {[job.error for job in jobs]}"
    )
    assert sum(job.result["component_count"] for job in jobs) == 56


async def test_three_concurrent_chunks_all_deplete(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    job_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The bill the chunker runs up: 84 distinct components is three jobs, and the runner's
    ``MAX_CONCURRENT_JOBS = 4`` starts them together. They contend on the same storeroom bin's
    quants and on the ISSUE move number sequence, whose row lock D-012 holds to commit. Every chunk
    must still COMPLETE and every ingredient must actually leave — a silently FAILED third chunk
    is the same missing COGS the dispatch cap would have caused, arriving by another road."""
    register_event_handlers()
    recipes = {
        f"DISH-{dish:02d}": {f"ING-{dish:02d}-{slot}": Decimal(1) for slot in range(7)}
        for dish in range(12)
    }
    kitchen = await build_kitchen(db_session, tenant_a, recipes, stock=Decimal(500))
    ticket_id = await build_open_ticket(
        db_session, tenant_a, [(kitchen.dishes[code], "1") for code in recipes]
    )

    with tenant_context(tenant_a):
        await run_in_uow(db_session, lambda: tickets.fire_ticket(db_session, tenant_a, ticket_id))
    job_ids = depletion.take_depletion_jobs(db_session)
    assert len(job_ids) == 3, "84 components must split into three chunks"
    for job_id in job_ids:  # scheduled together, exactly as the router does
        schedule_job(job_id, job_factory)
    await wait_for_jobs()

    jobs = await _jobs(db_session, tenant_a)
    assert [job.status for job in jobs] == [JobStatus.COMPLETED.value] * 3, (
        f"a concurrent chunk failed: {[job.error for job in jobs]}"
    )
    assert sum(job.result["component_count"] for job in jobs) == 84
    with tenant_context(tenant_a):
        for code in ("ING-00-0", "ING-05-3", "ING-11-6"):
            assert await inventory_queries.total_on_hand(
                db_session, tenant_a, kitchen.ingredients[code]
            ) == Decimal(499), f"{code} was never issued"
