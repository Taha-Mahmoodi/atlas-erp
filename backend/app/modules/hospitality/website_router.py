"""The property's own WEBSITE talking to Atlas (PLAN 19 Task 7, spec Q6).

Three routes on the same ``/api/v1/hospitality`` prefix as the staff router but a separate
``APIRouter``, because the caller is a different KIND of principal: a Phase 18 machine credential
(D-069) belonging to one first-party system, not a member of staff. Everything below is shaped by
that — the payloads carry no internal master data, the write takes no price, and each read declares
how long its answer may be reused.

**Two reads, two cache policies, and that split is the design.** Toast, Square and Lightspeed each
arrived at it independently: menu structure is slow-changing reference data, availability is
fast-changing state, and serving them together forces the slow half to the fast half's freshness.
So the menu is 60 s fresh with a long stale-if-error window, while availability is revalidated on
EVERY request against a collection ETag.

**Atlas cannot push invalidation.** D-011's bus is in-process and synchronous and there is no
outbound HTTP anywhere in app code, so the Toast/Square webhook pattern is unavailable: the website
PULLS, and the ``Cache-Control`` windows below are the contract rather than a fallback. They are
also the first ``Cache-Control`` in this codebase — until now only ETag was set.

**Why the menu read has no ETag, deliberately.** A collection ETag over ``Item`` would be a LYING
validator: ``collection_etag`` is ``COUNT(id), MAX(updated_at)``, prices live in
``sales_price_list_items``, and a reprice moves neither — so a revalidating website would receive a
304 asserting yesterday's price is current, forever. That is Q2's ETag trap one table over. Making
it truthful needs a second aggregate, which puts the read at five statements and breaches
PERFORMANCE §2. Bounding staleness with ``max-age=60`` instead is exactly the window Q6 contracts
for menu price, costs no query, and cannot lie. The endpoint where a validator actually earns its
keep — availability, ``no-cache, must-revalidate`` — keeps its ETag, and it is computed over the
one table this module owns, so it is correct by construction.

**The order write is the trust boundary.** ``OrderTicketLineCreate.unit_price`` is caller-supplied
and the ticket service trusts it; ``WebsiteOrderLine`` therefore has no such field and the price is
resolved server-side from the menu price list, narrowed to the tenant's functional currency so a
foreign-currency price can never be struck onto a check that carries no currency of its own
(D-019). It fires in the same transaction — a website order has no server to fire it later — and
then SCHEDULES the depletion jobs that firing submitted, after the uow commits. Forgetting that
drain loses only the scheduling, never the job row, but core has no stale-PENDING sweeper, so the
row would sit forever.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Request, Response

from app.core.conditional import collection_etag, conditional_response, request_fingerprint
from app.core.deps import CurrentUserDep, SessionDep, SessionFactoryDep
from app.core.events import run_in_uow
from app.core.exceptions import ValidationFailedError
from app.core.idempotency import Idempotent, IdempotentDep
from app.core.jobs import schedule_job
from app.core.models import utcnow
from app.core.pagination import MAX_LIMIT, CursorParams, cursor_params
from app.core.rbac import require_permission
from app.core.schemas import Page
from app.modules.finance import queries as finance_queries
from app.modules.hospitality import queries
from app.modules.hospitality.constants import (
    HOSPITALITY_MENU_READ,
    HOSPITALITY_TICKET_MANAGE,
)
from app.modules.hospitality.models import MenuAvailability
from app.modules.hospitality.schemas import (
    MenuAvailabilityPage,
    MenuAvailabilityRead,
    MenuItemRead,
    OrderTicketCreate,
    OrderTicketLineCreate,
    WebsiteOrderCreate,
    WebsiteOrderRead,
)
from app.modules.hospitality.service import availability, depletion, tickets
from app.modules.inventory import queries as inventory_queries
from app.modules.sales import queries as sales_queries

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-website"])

CursorParamsDep = Depends(cursor_params)
_MenuReadGuard = Depends(require_permission(HOSPITALITY_MENU_READ))
_OrderGuard = Depends(require_permission(HOSPITALITY_TICKET_MANAGE))
# A name of its own, not the staff router's "hospitality.order_ticket.create": D-013 reservations
# are scoped per endpoint, and a website replay must never collide with a terminal's.
_OrderIdempotentDep = Depends(Idempotent("hospitality.website_order.create"))

# Menu structure and price: 60 s fresh, then usable for 10 more minutes while a revalidation runs,
# and for a DAY if Atlas is unreachable — a restaurant with no ERP still has a menu, and serving an
# empty one is lost revenue. Safe only because the order response's total is authoritative.
MENU_CACHE_CONTROL = "private, max-age=60, stale-while-revalidate=600, stale-if-error=86400"
# The 86 board: never served without asking, because a stale "available" sells a dish that is gone.
# stale-if-error is short and fails OPEN by design — Q6 argues showing an unavailable dish is a
# normal restaurant apology, while showing nothing is not.
AVAILABILITY_CACHE_CONTROL = "no-cache, must-revalidate, stale-if-error=300"


@router.get("/menu", response_model=Page[MenuItemRead], dependencies=[_MenuReadGuard])
async def list_menu(
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    category_id: uuid.UUID | None = None,
) -> Page[MenuItemRead]:
    """The sellable menu: structure and price, keyset-paginated (D-014).

    THREE statements whatever the menu's size — the auth principal, one page of items, one batched
    price resolution over exactly that page (PERFORMANCE §2). The obvious alternative, resolving a
    price per dish, is 2 queries each; the derived-availability shape Q2 rejects is ~1,080 for a
    60-item menu.

    ``category_id`` is how a property scopes its menu, because Atlas ships no menu-membership
    entity: the hospitality industry template seeds a MENU item category and the website passes its
    id. Unfiltered, this is every ACTIVE item in the tenant — ingredients included — which is
    honest rather than convenient, and named in the docs.
    """
    response.headers["Cache-Control"] = MENU_CACHE_CONTROL
    page = await inventory_queries.list_active_items(
        session,
        current.tenant_id,
        category_id=category_id,
        cursor=params.cursor,
        limit=params.limit,
    )
    prices = await sales_queries.resolve_list_prices(
        session,
        current.tenant_id,
        item_ids=[item.id for item in page.items],
        on_date=date.today(),
    )
    return Page(
        items=[
            MenuItemRead(
                item_id=item.id,
                item_code=item.item_code,
                name=item.name,
                description=item.description,
                category_id=item.category_id,
                price=prices[item.id].unit_price if item.id in prices else None,
                currency_code=prices[item.id].currency_code if item.id in prices else None,
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        limit=page.limit,
    )


@router.get(
    "/menu/availability", response_model=MenuAvailabilityPage, dependencies=[_MenuReadGuard]
)
async def list_menu_availability(
    request: Request,
    response: Response,
    current: CurrentUserDep,
    session: SessionDep,
    cursor: str | None = None,
) -> MenuAvailabilityPage | Response:
    """The 86 board — every item the kitchen has said something about, and NOTHING else.

    Conditional GET (D-035) over ``hsp_menu_availability``, which is the whole reason Q2 stores
    availability rather than deriving it: ``collection_etag`` aggregates ``COUNT(id)`` and
    ``MAX(updated_at)``, so 86-ing a dish, clearing it, or a countdown reaching zero all move the
    validator — while an equivalent tag over ``inv_items`` would not move at all when the last
    portion sells, and the website would keep being told 304 for a dish that is gone.

    **NO ``limit`` PARAMETER, and the page is always ``MAX_LIMIT``.** Every other list in Atlas
    lets the client size its page; this one must not, because of the contract in
    ``MenuAvailabilityPage``: everything ABSENT from the board is available. Under the shared
    ``cursor_params`` default a property with 51 live overrides served 50 of them and told the
    website the rest were fine — a sold-out dish sold, which is the exact failure Q2 stores
    availability to prevent. ``as_of`` has the same dependency: it names ONE instant, and a board
    stitched from two requests was never in that state. The board is a handful of rows through a
    service (only overrides are stored), so serving it whole costs the same one statement.

    Past ``MAX_LIMIT`` overrides — outside the envelope spec Q6 contracts for — ``next_cursor``
    is non-null and the client MUST follow it; that is a v1 limit, stated, not a silent cut.

    A 304 costs ONE statement and returns no body; a 200 costs two. Absent items are available.
    """
    response.headers["Cache-Control"] = AVAILABILITY_CACHE_CONTROL
    fingerprint = request_fingerprint(cursor, MAX_LIMIT)
    # The third component is the whole reason this endpoint does not share the plain two-aggregate
    # validator every other reference list uses: expiry is LAZY, so a snooze lapsing changes the
    # answer without changing a row, and COUNT/MAX would hold still through it. It rides the same
    # aggregate select, so the 304 still costs one statement.
    etag = await collection_etag(
        session,
        MenuAvailability,
        request_fingerprint=fingerprint,
        extra_components=(availability.lapsed_count_expr(),),
    )

    async def builder() -> MenuAvailabilityPage:
        page = await queries.list_availability_overrides(
            session, current.tenant_id, cursor=cursor, limit=MAX_LIMIT
        )
        # ONE ``now`` for the whole page: the rows must be expired against a single instant, or two
        # rows on one page could be resolved against different clocks — which is also what ``as_of``
        # then honestly reports.
        now = utcnow()
        items = []
        for row in page.items:
            resolved = availability.resolve(row, now)
            items.append(
                MenuAvailabilityRead(
                    item_id=row.item_id,
                    state=resolved.state,
                    remaining_qty=resolved.remaining_qty,
                    available_until=resolved.available_until,
                    reason=resolved.reason,
                    source=resolved.source,
                )
            )
        return MenuAvailabilityPage(
            items=items, next_cursor=page.next_cursor, limit=page.limit, as_of=now
        )

    result = await conditional_response(request, response, etag, builder)
    if isinstance(result, Response):
        # The 304 is built inside conditional_response and carries only the ETag, so the cache
        # policy has to be restated on it — a validator with no policy is a client guess.
        result.headers["Cache-Control"] = AVAILABILITY_CACHE_CONTROL
    return result


@router.post(
    "/orders", response_model=WebsiteOrderRead, status_code=201, dependencies=[_OrderGuard]
)
async def place_website_order(
    payload: WebsiteOrderCreate,
    current: CurrentUserDep,
    session: SessionDep,
    factory: SessionFactoryDep,
    idem: IdempotentDep = _OrderIdempotentDep,
) -> WebsiteOrderRead:
    """Accept an order from the website: price it, open the check, and send it to the kitchen.

    IDEMPOTENT (D-013) and this is the endpoint that needs it most — a website retries a timed-out
    submit with the SAME key forever, and a second attempt must return the first ticket rather than
    cook the order twice. The published client contract matters here: a 409
    ``idempotency.in_progress`` means RETRY LATER WITH THE SAME KEY; minting a new key on a 409 is
    exactly how the duplicate this mechanism exists to prevent gets created.

    Firing inside the same request is what makes the 86 check and the countdown burn apply to a
    website order identically to a staff one — both go through ``fire_ticket``, which is the single
    commitment point (Q4). It is also why an 86'd dish comes back 422 rather than reaching a
    kitchen that cannot make it.
    """
    holder: dict[str, WebsiteOrderRead] = {}

    async def work() -> None:
        # The functional currency NARROWS price resolution. A ticket has no currency column — every
        # check is denominated in the tenant's functional currency (D-019) — so a price from a list
        # in another currency must not resolve at all. None (the v1 single-currency default) leaves
        # resolution unnarrowed, which is the same answer the menu read gives.
        currency = await finance_queries.functional_currency_or_none(session, current.tenant_id)
        item_ids = [line.item_id for line in payload.lines]
        prices = await sales_queries.resolve_list_prices(
            session,
            current.tenant_id,
            item_ids=item_ids,
            on_date=date.today(),
            currency=currency,
        )
        # Flattened to the one thing a line needs. A resolved row whose ``unit_price`` is None
        # cannot happen (``matched`` implies a price) but the type allows it, and the safe reading
        # of "I could not determine a price" is a refusal, never a zero.
        unit_prices = {
            item_id: resolved.unit_price
            for item_id, resolved in prices.items()
            if resolved.unit_price is not None
        }
        unpriced = [item_id for item_id in dict.fromkeys(item_ids) if item_id not in unit_prices]
        if unpriced:
            raise ValidationFailedError(
                message=(
                    "No menu price applies to these items"
                    + (f" in {currency}" if currency else "")
                    + f": {', '.join(str(item_id) for item_id in unpriced)}"
                ),
                code="hospitality.item_not_priced",
                details={"item_ids": [str(item_id) for item_id in unpriced]},
            )

        ticket = await tickets.create_ticket(
            session,
            current.tenant_id,
            OrderTicketCreate(
                table_code=payload.table_code,
                guest_count=payload.guest_count,
                notes=payload.notes,
                lines=[
                    OrderTicketLineCreate(
                        item_id=line.item_id,
                        quantity=line.quantity,
                        unit_price=unit_prices[line.item_id],
                        seat_number=line.seat_number,
                        notes=line.notes,
                    )
                    for line in payload.lines
                ],
            ),
        )
        ticket = await tickets.fire_ticket(session, current.tenant_id, ticket.id)
        await session.refresh(ticket)
        holder["read"] = await idem.capture(
            WebsiteOrderRead(
                ticket_id=ticket.id,
                ticket_number=ticket.ticket_number,
                status=ticket.status,
                opened_date=ticket.opened_date,
                total_amount=ticket.total_amount,
                currency_code=currency,
            ),
            status_code=201,
        )

    await run_in_uow(session, work)
    # AFTER the commit, never inside: the job rows are submitted by an event handler deep in the
    # uow and surface through this stash, and scheduling before the commit would race their
    # visibility to the runner's own session (core/jobs.py).
    for job_id in depletion.take_depletion_jobs(session):
        schedule_job(job_id, factory)
    return holder["read"]
