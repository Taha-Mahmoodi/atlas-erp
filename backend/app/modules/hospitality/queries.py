"""Hospitality's read surface: the staff ticket list and the derived at-risk menu list (PLAN 19
Tasks 6 and 7).

STRUCTURE §5 reserves ``queries.py`` for the reads OTHER modules import, and nothing imports
hospitality — it is the top of the dependency order. All three functions live here anyway, for one
reason each: ``at_risk_menu_items`` is where the plan's File Structure puts it; ``list_tickets`` and
``list_availability_overrides`` have nowhere better, because ``service/tickets.py`` is at the §8.4
400-line cap and a paginated read with no business rule in it does not justify a fourth service
file (the sales ``*_reads.py`` alternative). None of them writes anything.

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
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import as_utc
from app.core.pagination import (
    DEFAULT_LIMIT,
    OrderKey,
    SortDirection,
    filter_fingerprint,
    paginate,
)
from app.core.schemas import Page
from app.modules.hospitality.constants import OrderTicketStatus, ReservationStatus
from app.modules.hospitality.models import (
    MenuAvailability,
    MenuItemTag,
    MenuPlacement,
    MenuSection,
    OrderTicket,
    ServiceSlot,
    TableReservation,
)
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


async def list_availability_overrides(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[MenuAvailability]:
    """Every STORED availability override, keyset-paginated by item (D-014) — ONE statement.

    The 86 board as the website reads it, and note what it does NOT do: it does not enumerate the
    menu. The table only ever holds overrides (``clear_86`` deletes rather than storing an
    AVAILABLE row), so an item that is simply orderable is ABSENT, and the whole board stays a
    handful of rows through a service rather than growing with the menu. "Everything not listed is
    available" is the contract, which is also why the payload fits the one page spec Q6 requires.

    Rows come back RAW — lazy expiry is applied by the caller through ``availability.resolve``,
    the single place that rule lives. This function must not filter on ``available_until``: a
    lapsed row still has to appear so the reader is told the dish is back on.
    """
    stmt = select(MenuAvailability).where(MenuAvailability.tenant_id == tenant_id)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(MenuAvailability.item_id, SortDirection.ASC)],
        pk=MenuAvailability.id,
        cursor=cursor,
        limit=limit,
    )


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


async def slot_counters(
    session: AsyncSession, tenant_id: uuid.UUID, service_date: date
) -> dict[datetime, ServiceSlot]:
    """Every MATERIALISED pacing counter for one service date, keyed by its UTC slot instant.

    ONE statement whatever the night looks like (PERFORMANCE §2), served by the leading columns of
    ``uq_hsp_service_slots_tenant_id_service_date_slot_start``. The obvious alternative — asking the
    counter per slot as the grid is rendered — is 96 queries for a 24-hour service.

    Deliberately returns only what EXISTS. A slot with no row is not "closed", it is untouched, and
    the caller overlays the settings defaults onto the gaps (finding 3). Keying on ``as_utc`` is
    what makes the lookup work on both engines: aiosqlite round-trips ``DateTime(timezone=True)``
    as a naive value, so a raw key would never match the aware instant the caller is holding.
    """
    stmt = select(ServiceSlot).where(
        ServiceSlot.tenant_id == tenant_id, ServiceSlot.service_date == service_date
    )
    return {as_utc(row.slot_start): row for row in (await session.execute(stmt)).scalars()}


async def list_reservations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    service_date: date | None = None,
    status: ReservationStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[TableReservation]:
    """THE BOOK: a service's reservations in slot order (D-014 keyset, never OFFSET).

    Ascending by ``slot_start``, unlike the ticket list's newest-first: a book is read forward
    through the evening — the host works down it as parties arrive — so the natural first page is
    the start of service, not the most recent booking taken.

    The date and status filters are the two the floor uses ("tonight", "who has not shown"), and
    ``ix_hsp_table_reservations_tenant_id_service_date_slot_start`` serves the filter AND the sort.
    """
    stmt = select(TableReservation).where(TableReservation.tenant_id == tenant_id)
    if service_date is not None:
        stmt = stmt.where(TableReservation.service_date == service_date)
    if status is not None:
        stmt = stmt.where(TableReservation.status == status.value)
    return await paginate(
        session,
        stmt,
        order_by=[OrderKey(TableReservation.slot_start, SortDirection.ASC)],
        pk=TableReservation.id,
        cursor=cursor,
        limit=limit,
        filters=filter_fingerprint(service_date, status),
    )


# --- Menu structure (#212) ----------------------------------------------------


async def list_sections(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[MenuSection]:
    """The whole section tree in ONE statement, in the property's own running order.

    Unpaginated on purpose, and it is the same call the reservation grid makes: a menu's headings
    are tens of rows, bounded by what a kitchen can cook, and a paginated tree is a tree the client
    has to reassemble across pages. Ordered by depth-agnostic (sort_order, name) so the caller can
    nest it by ``parent_id`` and every sibling list is already correct.
    """
    stmt = (
        select(MenuSection)
        .where(MenuSection.tenant_id == tenant_id)
        .order_by(MenuSection.sort_order, MenuSection.name)
    )
    return list((await session.execute(stmt)).scalars().all())


async def dish_counts_by_section(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, int]:
    """{section_id -> how many dishes sit in it}, in ONE grouped statement — never a count per
    section, which is the N+1 a tree view invites."""
    stmt = (
        select(MenuPlacement.section_id, func.count())
        .where(MenuPlacement.tenant_id == tenant_id)
        .group_by(MenuPlacement.section_id)
    )
    return {section_id: count for section_id, count in (await session.execute(stmt)).all()}


async def placements_for_items(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """{item_id -> section_id} for the given dishes, in ONE statement. Items with no placement are
    absent from the mapping — unplaced is the default, so it costs no row and no entry."""
    if not item_ids:
        return {}
    stmt = select(MenuPlacement.item_id, MenuPlacement.section_id).where(
        MenuPlacement.tenant_id == tenant_id, MenuPlacement.item_id.in_(list(item_ids))
    )
    return {item_id: section_id for item_id, section_id in (await session.execute(stmt)).all()}


async def tags_for_items(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """{item_id -> [tag]} for the given dishes, in ONE statement, each list alphabetical."""
    if not item_ids:
        return {}
    stmt = (
        select(MenuItemTag.item_id, MenuItemTag.tag)
        .where(MenuItemTag.tenant_id == tenant_id, MenuItemTag.item_id.in_(list(item_ids)))
        .order_by(MenuItemTag.tag)
    )
    grouped: dict[uuid.UUID, list[str]] = defaultdict(list)
    for item_id, tag in (await session.execute(stmt)).all():
        grouped[item_id].append(tag)
    return grouped


async def all_placements(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[uuid.UUID, uuid.UUID]:
    """{item_id -> section_id} for every placed dish in the tenant, in ONE statement — the whole
    map, for a caller that is about to render the whole menu."""
    stmt = select(MenuPlacement.item_id, MenuPlacement.section_id).where(
        MenuPlacement.tenant_id == tenant_id
    )
    return {item_id: section_id for item_id, section_id in (await session.execute(stmt)).all()}


async def all_tags(session: AsyncSession, tenant_id: uuid.UUID) -> dict[uuid.UUID, list[str]]:
    """{item_id -> [tag]} for every tagged dish in the tenant, in ONE statement, each list
    alphabetical."""
    stmt = (
        select(MenuItemTag.item_id, MenuItemTag.tag)
        .where(MenuItemTag.tenant_id == tenant_id)
        .order_by(MenuItemTag.tag)
    )
    grouped: dict[uuid.UUID, list[str]] = defaultdict(list)
    for item_id, tag in (await session.execute(stmt)).all():
        grouped[item_id].append(tag)
    return grouped


async def item_ids_with_tag(
    session: AsyncSession, tenant_id: uuid.UUID, tag: str
) -> list[uuid.UUID]:
    """Every dish carrying ``tag`` — the filter the whole flat-tag shape exists to serve
    (D-081), served from ``ix_hsp_menu_item_tags_tenant_id_tag`` rather than a scan."""
    stmt = select(MenuItemTag.item_id).where(
        MenuItemTag.tenant_id == tenant_id, MenuItemTag.tag == tag.strip().lower()
    )
    return list((await session.execute(stmt)).scalars().all())


async def tags_in_use(session: AsyncSession, tenant_id: uuid.UUID) -> list[str]:
    """Every distinct tag the tenant has used, alphabetical — what a tag picker offers instead of
    a tag-master table nobody has to maintain (D-081)."""
    stmt = (
        select(MenuItemTag.tag)
        .where(MenuItemTag.tenant_id == tenant_id)
        .distinct()
        .order_by(MenuItemTag.tag)
    )
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "MenuItemAtRisk",
    "all_placements",
    "all_tags",
    "at_risk_menu_items",
    "dish_counts_by_section",
    "item_ids_with_tag",
    "list_availability_overrides",
    "list_reservations",
    "list_sections",
    "list_tickets",
    "placements_for_items",
    "slot_counters",
    "tags_for_items",
    "tags_in_use",
]
