"""Ingredient depletion (PLAN 19 Task 5, spec Q4): aggregate the recipe explosion, then issue it in
a BACKGROUND job — never in the transaction that sells the food.

**Why not synchronously.** Q4 measured it. One ingredient ISSUE move is 38 SQL statements
(``tests/perf/test_write_budgets.py`` re-measures it on every run) and 24 lines is 911, but the
statement count is not what breaks first:

* ``MAX_DISPATCHES_PER_UOW = 50`` (``core/events.py``) counts handler INVOCATIONS, so 51 issue
  lines raise ``EventCycleError`` → HTTP 500. An 8-top ordering 8 dishes at 7 ingredients is 56
  raw lines: *the guest cannot pay their bill, and the error is a 500.*
* ``apply_bin_delta`` raises ``InsufficientStockError`` when a component would go negative and
  D-011 rolls the WHOLE uow back — so a phantom stock-out REFUSES SERVICE on stock the industry's
  own benchmark says is permanently 2-5% wrong (actual-vs-theoretical variance under 2% is
  well-run; over 5% is systematic).
* ``claim_number`` holds the tenant's sequence row lock to COMMIT by construction (D-012
  gaplessness), so a long settlement serializes every other posting in the tenant — the hotel's
  included.

**The shape**, three pieces:

1. **Aggregate** across the ticket's lines before issuing anything. A check whose dishes share
   onion, oil and salt collapses ~24 raw lines to ~12 distinct items; that roughly halves the
   statement count and is what puts the dispatch cap out of reach.
2. **Background** it. ``handlers.submit_ticket_depletion`` submits the job inside the FIRE's uow,
   so the PENDING row and the ticket's SENT_TO_KITCHEN status commit together and a D-013 replay
   returns the same job id rather than depleting twice.
3. **Chunk** it at ``DEPLETE_MAX_COMPONENTS_PER_JOB``. Backgrounding alone does NOT lift the
   dispatch cap — the runner executes handlers inside ``run_in_uow`` too (``core/jobs.py``) — so a
   pathological aggregate becomes several jobs instead of one ``EventCycleError``.

**What is traded** (Task 8 records it in DECISIONS, restaurant-module-scoped, NOT a platform-wide
relaxation of D-011): between fire and job completion the ticket has revenue with no COGS, and a
depletion that used to fail loudly at the guest's table now fails quietly as a FAILED job row. That
second one must be bought back with FAILED-job alerting, and it lands on a pre-existing core gap —
there is no stale-PENDING sweeper. What actually breaks is the unstated coupling "the sale and its
depletion commit together"; D-011 itself is untouched, because the job's own uow still guarantees
that a goods issue without its COGS journal can never commit.

Nothing here calls inventory's service: hospitality publishes ``TicketIngredientsConsumed`` and
inventory's handler creates the moves (STRUCTURE §5), the same bridge sales' delivery and
manufacturing's component issue already use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import batched
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.core.exceptions import ValidationFailedError
from app.core.jobs import register_job
from app.core.money import quantize_quantity
from app.modules.hospitality.constants import (
    DEPLETE_MAX_COMPONENTS_PER_JOB,
    DEPLETE_TICKET_JOB,
)
from app.modules.hospitality.events import ConsumedIngredient, TicketIngredientsConsumed
from app.modules.hospitality.service.tickets import get_ticket, get_ticket_lines
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing import queries as mfg_queries

# Per-transaction stash of the job ids a fire submitted, keyed in ``session.info`` exactly like the
# D-011 event buffer and the D-010 audit buffer — per-session, never shared across requests. A job
# must be SCHEDULED strictly after its PENDING row commits (core/jobs.py), and the fire's submitter
# is an event handler deep inside the uow, so the ids surface here for the router to drain after
# ``run_in_uow`` returns. See :func:`take_depletion_jobs`.
_JOBS_KEY = "hospitality_depletion_jobs"


@dataclass(frozen=True)
class ComponentDemand:
    """One distinct ingredient a ticket consumes, summed across every line that uses it.
    ``quantity`` is in the item's BASE UoM — a ticket line's quantity always is (no ``uom_id`` on
    the line), and a BOM explodes against the same basis, so nothing here converts units."""

    item_id: uuid.UUID
    quantity: Decimal


async def aggregate_components(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> list[ComponentDemand]:
    """Explode a ticket's dishes into their ingredients and SUM per distinct ingredient (Q4).

    THREE queries whatever the ticket's size: the lines, then the ACTIVE default BOMs for the
    distinct dishes, then those BOMs' components — the batched manufacturing reads exist so a
    multi-parent explosion never loops the singular ones.

    Single-level, matching ``create_production_order``: a prepped sub-recipe (a sauce, a stock) is
    produced by its own order and consumed here as the stock item it is.

    A dish with NO active BOM depletes ITSELF. A bottled beer is a sellable inventory item with no
    recipe, and reading "no BOM" as "nothing to deplete" would make its stock silently never move —
    worse than the loud FAILED job an un-entered recipe produces, because Q4's whole concession
    rests on depletion failures being visible.
    """
    lines = await get_ticket_lines(session, tenant_id, ticket_id)
    sold: dict[uuid.UUID, Decimal] = {}
    for line in lines:
        sold[line.item_id] = sold.get(line.item_id, Decimal(0)) + Decimal(line.quantity)

    boms = await mfg_queries.active_boms_for_items(session, tenant_id, list(sold))
    components = await mfg_queries.components_for_boms(
        session, tenant_id, [bom.id for bom in boms.values()]
    )

    demand: dict[uuid.UUID, Decimal] = {}
    for item_id, quantity in sold.items():
        bom = boms.get(item_id)
        if bom is None:
            demand[item_id] = demand.get(item_id, Decimal(0)) + quantity
            continue
        base_quantity = Decimal(str(bom.base_quantity))
        for component in components.get(bom.id, []):
            scrap_factor = Decimal(1) + (Decimal(str(component.scrap_percent)) / Decimal(100))
            required = quantize_quantity(
                (Decimal(str(component.quantity_per)) * quantity / base_quantity) * scrap_factor
            )
            if required > 0:
                key = component.component_item_id
                demand[key] = demand.get(key, Decimal(0)) + required
    return [
        ComponentDemand(item_id=item_id, quantity=quantity)
        for item_id, quantity in sorted(demand.items(), key=lambda pair: pair[0].bytes)
    ]


def job_payloads(
    ticket_id: uuid.UUID, components: list[ComponentDemand], *, move_date: date
) -> list[dict[str, Any]]:
    """Split an aggregate into one job payload per ``DEPLETE_MAX_COMPONENTS_PER_JOB`` components.

    Payloads carry the exploded quantities rather than just the ticket id, which SNAPSHOTS the
    recipe at fire time: a chef editing a BOM mid-service must not retroactively change what an
    already-cooked ticket consumed. Values are JSON primitives (``core_jobs.payload`` is JSON) and
    quantities are decimal STRINGS (D-015 — a float would lose the sixth place).
    """
    return [
        {
            "ticket_id": str(ticket_id),
            "move_date": move_date.isoformat(),
            "components": [
                {"item_id": str(component.item_id), "quantity": str(component.quantity)}
                for component in chunk
            ],
        }
        for chunk in batched(components, DEPLETE_MAX_COMPONENTS_PER_JOB)
    ]


def remember_job(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Record a submitted depletion job for the router to schedule after the uow commits."""
    session.info.setdefault(_JOBS_KEY, []).append(job_id)


def take_depletion_jobs(session: AsyncSession) -> tuple[uuid.UUID, ...]:
    """Pop the depletion jobs this transaction submitted (empty when the fire submitted none).

    A router that fires a ticket calls this immediately AFTER ``run_in_uow`` returns and passes
    each id to ``schedule_job(job_id, factory)`` — scheduling before the commit would race the
    PENDING row's visibility, which is why ``count_router``/``fx_router`` schedule post-commit too.
    Popping (not reading) means a session reused for a second request cannot re-schedule a job that
    already ran.

    ONLY on the success path. If ``run_in_uow`` raised, the exception propagates past the call site
    and the stashed ids die with the request's session (core/deps opens one per request) — there is
    no rolled-back job row to schedule, because the INSERT rolled back with everything else.
    """
    return tuple(session.info.pop(_JOBS_KEY, ()))


async def deplete_ticket(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    components: list[ComponentDemand],
    *,
    move_date: date,
) -> None:
    """Issue an aggregated ingredient list off the storeroom — the engine both the job handler and
    any future replay path go through.

    Resolves every component's source bin in ONE query (an N+1 here would multiply by every
    ingredient on every ticket) and publishes ``TicketIngredientsConsumed``; inventory's handler
    creates the ISSUE moves and their COGS journals in this same transaction.

    An ingredient with no stock ANYWHERE has no bin to issue from and raises
    ``hospitality.component_out_of_stock`` — which, running inside the job, is a FAILED job row and
    NOT a guest who cannot pay (Q4). All the ids are reported at once, so a kitchen fixing a
    depletion sees every problem ingredient rather than the first.
    """
    ticket = await get_ticket(session, tenant_id, ticket_id)
    bins = await inventory_queries.issue_bins_for_items(
        session, tenant_id, [component.item_id for component in components]
    )
    missing = sorted(str(c.item_id) for c in components if c.item_id not in bins)
    if missing:
        # The ids go in the MESSAGE, not only in ``details``: core/jobs.py records a failure as
        # ``str(exc)``, so anything left in details is invisible to whoever reads the FAILED row —
        # and an unreadable failure is exactly the concession Q4 warns must be bought back.
        raise ValidationFailedError(
            message=(
                f"No stock to issue for {len(missing)} ingredient(s) on ticket "
                f"{ticket.ticket_number}: {', '.join(missing)}"
            ),
            code="hospitality.component_out_of_stock",
            details={"ticket_id": str(ticket_id), "item_ids": missing},
        )
    publish(
        session,
        TicketIngredientsConsumed(
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            document_id=ticket.document_id,
            move_date=move_date.isoformat(),
            ingredients=tuple(
                ConsumedIngredient(
                    item_id=component.item_id,
                    bin_id=bins[component.item_id],
                    quantity=component.quantity,
                )
                for component in components
            ),
        ),
    )


@register_job(DEPLETE_TICKET_JOB)
async def deplete_ticket_job(
    session: AsyncSession, tenant_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    """Issue one fired ticket's aggregated ingredients off-request (Q4) — a thin delegation to
    :func:`deplete_ticket`, the ``count_post_job`` shape.

    The runner restores the submitting tenant context (D-007) and the D-010 actor and runs this
    inside ``run_in_uow`` (``core/jobs.py``), so D-011's actual invariant — a goods issue without
    its COGS journal can never commit — still holds, and the COMPLETED status commits with the
    moves. What moved is the transaction boundary, not the guarantee.
    """
    ticket_id = uuid.UUID(payload["ticket_id"])
    components = [
        ComponentDemand(item_id=uuid.UUID(row["item_id"]), quantity=Decimal(row["quantity"]))
        for row in payload["components"]
    ]
    await deplete_ticket(
        session,
        tenant_id,
        ticket_id,
        components,
        move_date=date.fromisoformat(payload["move_date"]),
    )
    return {
        "ticket_id": str(ticket_id),
        "component_count": len(components),
        "move_date": payload["move_date"],
    }


__all__ = [
    "ComponentDemand",
    "aggregate_components",
    "deplete_ticket",
    "deplete_ticket_job",
    "job_payloads",
    "remember_job",
    "take_depletion_jobs",
]
