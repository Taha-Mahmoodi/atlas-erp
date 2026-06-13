"""The condition-style price resolver (PLAN 7.1, D-043): resolve the applicable base unit price for
an item + customer + date + quantity + currency.

This is the v1 pricing engine the s4hana-parity Sales section scopes to: price lists by
currency/customer-group/date-range with a base price per item — NOT the generalized access-sequence
engine. ``resolve_price`` is the single deterministic best-match picker; it is exposed to other
modules via ``sales/queries.resolve_price`` (7.2's order entry prices each line through it).

**Deterministic resolution order (D-043).** Among the price lists that APPLY — i.e. all of:

1. ``status == ACTIVE`` (INACTIVE lists are never priced from);
2. ``currency_code == currency`` (a list prices in exactly one currency);
3. ``valid_from <= on_date`` AND (``valid_to IS NULL`` OR ``valid_to >= on_date``) — the date is in
   the inclusive window;
4. the list is GENERAL (``customer_group_id IS NULL``) OR targets the customer's group
   (``customer_group_id == customer.customer_group_id``); a list targeting a DIFFERENT group, or
   any group when the customer has none, does not apply;
5. the list has a ``PriceListItem`` for ``item_id`` whose ``min_quantity <= quantity``;

the winner is chosen by, in strict order:

  a. **highest ``priority``** (the explicit tenant override; higher integer wins);
  b. then **most specific**: a GROUP-TARGETED list beats a GENERAL (null-group) list;
  c. then **latest ``valid_from``** (the most recently effective list wins — a newer campaign price
     supersedes an older one);
  d. then **price-list ``id``** as a final stable tiebreaker (so the result is fully deterministic
     even for two otherwise-identical lists — pathological, but the order must never depend on row
     order).

If nothing applies, the resolver returns a "no match" result; 7.2's order entry then requires a
manual price or an override. NO discount is applied here — the price list yields the base price only
(discounts are a per-order-line concern in 7.2).

**Boundedness (PERFORMANCE §6, no N+1).** Two queries total, regardless of how many lists exist:
ONE query fetches the small set of candidate ACTIVE lists matching currency+date+group (index-served
by ``ix_sales_price_lists_resolver``); ONE query fetches, for those candidate lists, the
``PriceListItem`` rows for this item meeting ``min_quantity`` (index-served by
``ix_sales_price_list_items_tenant_id_item_id``). The winner is then picked in Python over that
small joined set — no per-list round trip.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sales.constants import PriceListStatus
from app.modules.sales.models import Customer, PriceList, PriceListItem


@dataclass(frozen=True)
class ResolvedPrice:
    """The outcome of ``resolve_price`` (D-043). ``matched`` False means no ACTIVE price list
    applied
    (all price fields None). When matched, ``unit_price`` is the base price in ``currency_code`` and
    ``price_list_id`` / ``price_list_code`` name the winning list. No discount is applied (base
    price
    only)."""

    matched: bool
    unit_price: Decimal | None = None
    price_list_id: uuid.UUID | None = None
    price_list_code: str | None = None
    currency_code: str | None = None


_NO_MATCH = ResolvedPrice(matched=False)


async def resolve_price(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    customer_id: uuid.UUID,
    on_date: date,
    quantity: Decimal,
    currency: str,
) -> ResolvedPrice:
    """Resolve the applicable base unit price for an item/customer/date/quantity/currency (D-043).

    Returns a :class:`ResolvedPrice`; ``matched`` is False (all price fields None) when no ACTIVE
    price list applies. The deterministic best-match order is documented at the top of this module.
    Bounded to two queries (the candidate lists, then their items for this item) — no N+1.
    """
    customer = (
        await session.execute(
            select(Customer.customer_group_id).where(
                Customer.tenant_id == tenant_id, Customer.id == customer_id
            )
        )
    ).first()
    if customer is None:
        # An unknown customer cannot have a resolved price — the caller (7.2) validates the customer
        # exists before pricing, so this is a defensive no-match rather than an error path.
        return _NO_MATCH
    customer_group_id = customer[0]

    # Query 1: the candidate ACTIVE lists matching currency + date window + (general OR this
    # customer's group). A list targeting a different group is excluded in SQL; a list targeting
    # ANY group is excluded when the customer has none (the `is_(None)` arm only).
    group_match = PriceList.customer_group_id.is_(None)
    if customer_group_id is not None:
        group_match = group_match | (PriceList.customer_group_id == customer_group_id)
    candidate_stmt = select(PriceList).where(
        PriceList.tenant_id == tenant_id,
        PriceList.status == PriceListStatus.ACTIVE.value,
        PriceList.currency_code == currency,
        PriceList.valid_from <= on_date,
        (PriceList.valid_to.is_(None)) | (PriceList.valid_to >= on_date),
        group_match,
    )
    candidates = list((await session.execute(candidate_stmt)).scalars().all())
    if not candidates:
        return _NO_MATCH

    # Query 2: the price rows for THIS item on the candidate lists that meet the quantity floor.
    candidate_ids = [pl.id for pl in candidates]
    item_stmt = select(PriceListItem).where(
        PriceListItem.tenant_id == tenant_id,
        PriceListItem.item_id == item_id,
        PriceListItem.price_list_id.in_(candidate_ids),
        PriceListItem.min_quantity <= quantity,
    )
    item_rows = list((await session.execute(item_stmt)).scalars().all())
    if not item_rows:
        return _NO_MATCH

    # Join the price rows to their lists in Python (the candidate set is small) and pick the winner
    # by the D-043 sort key: priority desc, specificity (group-targeted > general) desc, valid_from
    # desc, then list id as the final stable tiebreaker.
    lists_by_id = {pl.id: pl for pl in candidates}

    def sort_key(row: PriceListItem) -> tuple[int, int, date, str]:
        pl = lists_by_id[row.price_list_id]
        is_group_targeted = 1 if pl.customer_group_id is not None else 0
        return (pl.priority, is_group_targeted, pl.valid_from, str(pl.id))

    winner_row = max(item_rows, key=sort_key)
    winner_list = lists_by_id[winner_row.price_list_id]
    return ResolvedPrice(
        matched=True,
        unit_price=Decimal(str(winner_row.unit_price)),
        price_list_id=winner_list.id,
        price_list_code=winner_list.code,
        currency_code=winner_list.currency_code,
    )
