"""Hospitality's read surface: the staff ticket list and the derived at-risk menu list (PLAN 19
Task 6).

STRUCTURE §5 reserves ``queries.py`` for the reads OTHER modules import, and nothing imports
hospitality — it is the top of the dependency order. Both functions live here anyway, for one
reason each: ``at_risk_menu_items`` is where the plan's File Structure puts it, and ``list_tickets``
has nowhere better, because ``service/tickets.py`` is at the §8.4 400-line cap and a paginated read
with no business rule in it does not justify a fourth service file (the sales ``*_reads.py``
alternative). Neither writes anything.

**The at-risk list is the ONE place derived recipe math is allowed in this phase**, and it earns it
by being staff-facing and advisory. Q2 rejects derivation for the guest-facing answer on three
grounds — ~1,080 queries for a 60-item menu, an ``on_hand - committed + on_order`` formula that
lets tomorrow's delivery sell tonight's dish, and a ``collection_etag`` that never invalidates
because selling a portion moves no ``Item.updated_at``. None of the three bites here: the scan is
two queries flat, it reads ON-HAND ONLY, and nothing caches it. It says "beef covers no more
steaks"; **a human 86s**, which writes the stored row the website actually reads.

It over-reports on shared ingredients by construction — every dish is costed against the whole
storeroom, so ten dishes sharing one onion each read as fully coverable. That is exactly why it
must never be the number a guest sees.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.hospitality.constants import OrderTicketStatus
from app.modules.hospitality.models import OrderTicket
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing import queries as mfg_queries


@dataclass(frozen=True)
class MenuItemAtRisk:
    """How many more portions of one dish the storeroom covers, and which ingredient runs out
    first. ``max_producible`` is floored to whole portions — half a plate is not sellable."""

    item_id: uuid.UUID
    max_producible: int
    limiting_item_id: uuid.UUID


async def at_risk_menu_items(
    session: AsyncSession, tenant_id: uuid.UUID, *, threshold: int, limit: int
) -> list[MenuItemAtRisk]:
    """Dishes the storeroom covers ``threshold`` portions or fewer of, worst first.

    TWO queries whatever the menu's size (PERFORMANCE §2), and both are set-based: one whole-tenant
    BOM explosion, then one batched on-hand read over the distinct ingredients it named. The naive
    shape — ``atp_check`` per dish — is 3 queries per item, ~1,080 for a 60-item menu (Q2).

    ON-HAND ONLY. Dropping ``committed`` and ``on_order`` from the ATP formula is the correction,
    not an omission: a kitchen cannot cook an open purchase order, and a sales reservation on an
    ingredient is not what stops the pass from plating.

    Sorted ascending so a truncated list is the end a chef needs. ``limit`` bounds the response;
    the SCAN is the tenant's whole active-default-BOM set, which for a property is its menu (tens
    of dishes). A tenant with thousands of manufacturing BOMs is out of this endpoint's scope —
    bounding the scan itself needs a menu-membership concept Phase 19 does not ship.
    """
    requirements = await mfg_queries.active_bom_requirements(session, tenant_id)
    if not requirements:
        return []
    component_ids = {
        component_id
        for components in requirements.values()
        for component_id in components
    }
    on_hand = await inventory_queries.on_hand_for_items(session, tenant_id, component_ids)

    at_risk: list[MenuItemAtRisk] = []
    for item_id, components in requirements.items():
        producible: tuple[int, uuid.UUID] | None = None
        for component_id, per_unit in components.items():
            if per_unit <= 0:  # a zero-quantity BOM line consumes nothing and limits nothing
                continue
            portions = int(on_hand.get(component_id, Decimal(0)) // per_unit)
            if producible is None or portions < producible[0]:
                producible = (portions, component_id)
        if producible is not None and producible[0] <= threshold:
            at_risk.append(
                MenuItemAtRisk(
                    item_id=item_id,
                    max_producible=producible[0],
                    limiting_item_id=producible[1],
                )
            )
    # item_id.bytes breaks ties deterministically, so a paging client sees a stable order.
    at_risk.sort(key=lambda row: (row.max_producible, row.item_id.bytes))
    return at_risk[:limit]


async def list_tickets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: OrderTicketStatus | None = None,
    opened_on: date | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[OrderTicket]:
    """The floor's checks, newest service date first (D-014 keyset, never OFFSET).

    The status and date filters are the two the floor and the kitchen display actually use, and
    they are served by ``ix_hsp_order_tickets_tenant_id_opened_date_status`` — the index exists for
    this query. Sorting on ``opened_date`` (a DATE) rather than ``created_at`` keeps a service that
    runs past midnight on one date.
    """
    stmt = select(OrderTicket).where(OrderTicket.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(OrderTicket.status == status.value)
    if opened_on is not None:
        stmt = stmt.where(OrderTicket.opened_date == opened_on)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(OrderTicket.opened_date, SortDirection.DESC)],
        pk=OrderTicket.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(status, opened_on),
    )


__all__ = ["MenuItemAtRisk", "at_risk_menu_items", "list_tickets"]
