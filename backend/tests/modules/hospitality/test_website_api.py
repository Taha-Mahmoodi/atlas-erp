"""The property's website talking to Atlas over the Phase 18 machine credential (PLAN 19 Task 7).

Three endpoints, and every test here is about one of the three things spec Q6 says the pair of
reads plus the one write have to get right:

1. **Two reads, two cache policies.** The menu is structure + price (slow, 60 s fresh); availability
   is the 86 board (fast, revalidated on every request). They are separate resources because they
   change at completely different rates — the split Toast, Square and Lightspeed each made
   independently.
2. **The validator has to MOVE when the answer changes.** Q2's ETag trap is the reason availability
   is stored rather than derived; the tests below assert the trap is actually shut — 86-ing a dish
   changes the availability ETag, so a website revalidating cannot be told "304, still available".
3. **The write is idempotent and prices itself.** A website retries on a timeout, so a replay must
   return the first ticket rather than send the kitchen a second copy; and the ORDER BODY CARRIES NO
   PRICE, so a caller cannot order a steak for nothing.

The credential is a real ``core_api_keys`` row (D-069), not a JWT: these tests are the only place
in the module suite where the principal is a machine, and the 403 test drives a SCOPED key to prove
D-069's intersection actually confines the website to what it was issued for.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import Job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import (
    DEPLETE_TICKET_JOB,
    AvailabilityState,
    OrderTicketStatus,
)
from app.modules.hospitality.service import availability
from tests.conftest import QueryCounter
from tests.modules.hospitality.conftest import MENU_PRICES, WebsiteApi
from tests.modules.hospitality.factories import build_dish, build_menu_price

MENU_URL = "/api/v1/hospitality/menu"
AVAILABILITY_URL = "/api/v1/hospitality/menu/availability"
ORDERS_URL = "/api/v1/hospitality/orders"


def _order(item_id: uuid.UUID, quantity: str = "1") -> dict[str, object]:
    return {"table_code": "WEB", "lines": [{"item_id": str(item_id), "quantity": quantity}]}


async def _jobs(session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    with tenant_context(tenant_id):
        await session.commit()  # see the job rows the request's own session committed
        rows = await session.execute(select(Job).where(Job.job_type == DEPLETE_TICKET_JOB))
        return list(rows.scalars().all())


# --- The menu read ------------------------------------------------------------


async def test_the_menu_read_stays_within_the_query_budget(
    website_api: WebsiteApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """PERFORMANCE §2 at menu scale, and the property that rule exists to protect: the statement
    count must not GROW with the number of dishes. Q2 measured the naive per-item shape
    (``atp_check`` per dish) at ~1,080 statements for a 60-item menu."""
    await website_api.client.get(MENU_URL)  # warm the D-009 RBAC TTL cache

    with query_counter() as small:
        first = await website_api.client.get(MENU_URL)
    assert first.status_code == 200, first.text
    small_rows = len(first.json()["items"])

    for index in range(20):
        await build_dish(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.setup,
            item_code=f"EXTRA-{index:02d}",
            recipe={},
        )
    with query_counter() as large:
        second = await website_api.client.get(MENU_URL, params={"limit": 200})
    assert second.status_code == 200, second.text

    assert len(second.json()["items"]) == small_rows + 20
    assert large.count == small.count, (
        f"the menu read grew from {small.count} to {large.count} statements on 20 more dishes:\n"
        + "\n".join(large.statements)
    )
    # >= 1 keeps the equality above from passing vacuously on a counter that never fired.
    assert 1 <= small.count <= 3, (
        f"the menu read ran {small.count} statements (PERFORMANCE §2 budgets 3):\n"
        + "\n".join(small.statements)
    )


async def test_the_menu_prices_every_dish_as_a_decimal_string(website_api: WebsiteApi) -> None:
    """D-015: money crosses the wire as a decimal STRING, never a float — a website that parses a
    float price and multiplies it is how a check ends up a cent out."""
    response = await website_api.client.get(MENU_URL)
    assert response.status_code == 200, response.text

    by_code = {row["item_code"]: row for row in response.json()["items"]}
    pasta = by_code["PASTA"]
    assert isinstance(pasta["price"], str)
    assert Decimal(pasta["price"]) == MENU_PRICES["PASTA"]
    assert pasta["currency_code"] == "USD"
    # An ingredient carries no menu price. It is still listed (hiding it would hide the
    # misconfiguration); the order endpoint is what refuses to sell it.
    assert by_code["TOMATO"]["price"] is None


async def test_the_menu_carries_its_cache_policy(website_api: WebsiteApi) -> None:
    """Atlas cannot push invalidation (D-011's bus is in-process, no outbound HTTP anywhere), so
    the website pulls and these staleness windows ARE the contract, not a fallback (Q6)."""
    response = await website_api.client.get(MENU_URL)
    cache_control = response.headers["cache-control"]
    assert "max-age=60" in cache_control
    assert "stale-if-error=86400" in cache_control


# --- The availability read ----------------------------------------------------


async def test_availability_304s_on_an_unchanged_etag(website_api: WebsiteApi) -> None:
    first = await website_api.client.get(AVAILABILITY_URL)
    assert first.status_code == 200, first.text
    again = await website_api.client.get(
        AVAILABILITY_URL, headers={"If-None-Match": first.headers["etag"]}
    )
    assert again.status_code == 304
    assert "no-cache" in again.headers["cache-control"]


async def test_86ing_a_dish_changes_the_availability_etag(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The ETag trap in reverse (Q2). ``collection_etag`` is ``COUNT(id), MAX(updated_at)``, so a
    validator computed over ``inv_items`` would NOT move when the last portion sells and the website
    would keep receiving a 304 asserting a sold-out dish is available. Computing it over the STORED
    availability row is what shuts the trap."""
    before = (await website_api.client.get(AVAILABILITY_URL)).headers["etag"]

    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.dishes["PASTA"],
            state=AvailabilityState.EIGHTY_SIXED,
            reason="out of basil",
        )
        await db_session.commit()

    after = await website_api.client.get(AVAILABILITY_URL)
    assert after.headers["etag"] != before
    rows = {row["item_id"]: row for row in after.json()["items"]}
    eighty_sixed = rows[str(website_api.kitchen.dishes["PASTA"])]
    assert eighty_sixed["state"] == AvailabilityState.EIGHTY_SIXED.value
    assert eighty_sixed["reason"] == "out of basil"
    assert after.json()["as_of"] is not None


# --- The order write ----------------------------------------------------------


async def test_a_scoped_key_cannot_post_an_order(
    website_api: WebsiteApi, client: AsyncClient
) -> None:
    """D-069 scopes INTERSECT the bound user's permissions, so a key issued for the menu read
    cannot place an order even though its user could."""
    client.headers["Authorization"] = f"Bearer {website_api.read_only_key}"
    response = await client.post(
        ORDERS_URL,
        json=_order(website_api.kitchen.dishes["PASTA"]),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 403, response.text


async def test_an_order_fires_the_ticket_and_carries_the_authoritative_total(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The menu price is cached for 60 s, so the website must display the total ATLAS returns
    before payment, never one it computed from a cached price (Q6). The ticket is already
    SENT_TO_KITCHEN: a website order has no server to fire it later."""
    response = await website_api.client.post(
        ORDERS_URL,
        json={
            "table_code": "WEB",
            "lines": [
                {"item_id": str(website_api.kitchen.dishes["PASTA"]), "quantity": "2"},
                {"item_id": str(website_api.kitchen.dishes["BEER"]), "quantity": "1"},
            ],
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text

    body = response.json()
    assert isinstance(body["total_amount"], str)  # D-015
    assert Decimal(body["total_amount"]) == MENU_PRICES["PASTA"] * 2 + MENU_PRICES["BEER"]
    assert body["currency_code"] == "USD"
    assert body["status"] == OrderTicketStatus.SENT_TO_KITCHEN.value
    assert body["ticket_number"].startswith("TKT-")

    await wait_for_jobs()
    assert len(await _jobs(db_session, website_api.tenant_id)) == 1, (
        "firing must submit exactly one depletion job, and the route must schedule it after its "
        "uow commits — core has no stale-PENDING sweeper"
    )


async def test_a_replayed_order_does_not_create_two_tickets(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """D-013: the website retries on a timeout with the SAME key forever, and must not double-fire
    the kitchen — nor submit a second depletion job against the same stock."""
    body = _order(website_api.kitchen.dishes["PASTA"])
    key = str(uuid.uuid4())

    first = await website_api.client.post(ORDERS_URL, json=body, headers={"Idempotency-Key": key})
    second = await website_api.client.post(ORDERS_URL, json=body, headers={"Idempotency-Key": key})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["ticket_id"] == second.json()["ticket_id"]
    assert second.headers.get("Idempotency-Replayed") == "true"

    await wait_for_jobs()
    assert len(await _jobs(db_session, website_api.tenant_id)) == 1


async def test_an_order_cannot_name_its_own_price(website_api: WebsiteApi) -> None:
    """The trust boundary. ``OrderTicketLineCreate.unit_price`` is caller-supplied and the service
    trusts it; the WEBSITE shape has no such field, so a request carrying one is rejected outright
    rather than silently ignored."""
    response = await website_api.client.post(
        ORDERS_URL,
        json={
            "lines": [
                {
                    "item_id": str(website_api.kitchen.dishes["PASTA"]),
                    "quantity": "1",
                    "unit_price": "0.01",
                }
            ]
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text


async def test_an_unpriced_item_is_refused(website_api: WebsiteApi) -> None:
    """An ingredient is on no menu price list, so there is no price to strike the check at. Refused
    loudly rather than sold at zero."""
    response = await website_api.client.post(
        ORDERS_URL,
        json=_order(website_api.kitchen.ingredients["TOMATO"]),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.item_not_priced"


async def test_a_foreign_currency_price_is_never_charged(website_api: WebsiteApi) -> None:
    """The ticket carries NO currency column — every check is denominated in the tenant's
    functional currency (D-019) — so a dish priced only in EUR has no price this property may
    charge, and the order is refused rather than silently struck at the EUR number.

    The dish IS on the menu read (which does not narrow by currency and labels each price with the
    currency it resolved), so this is also the one place the two surfaces can disagree, and it
    disagrees safely: a visible price, a refused order, never a wrong charge.
    """
    response = await website_api.client.post(
        ORDERS_URL,
        json=_order(website_api.euro_only_dish_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.item_not_priced"


async def test_an_86ed_dish_cannot_be_ordered_from_the_website(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The stored 86 is the guest-facing answer, and it is enforced at FIRE — which a website order
    reaches in the same request, so a cached menu cannot sell what the kitchen has run out of."""
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.dishes["PASTA"],
            state=AvailabilityState.EIGHTY_SIXED,
        )
        await db_session.commit()

    response = await website_api.client.post(
        ORDERS_URL,
        json=_order(website_api.kitchen.dishes["PASTA"]),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.item_unavailable"


async def test_a_phantom_stock_out_does_not_refuse_the_order(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """Q4's whole concession, end to end: STEAK's recipe needs 20 BEEF against 10 in the storeroom.
    Depletion is BACKGROUND, so the guest is served and the shortage surfaces as a FAILED job —
    restaurant theoretical stock is permanently 2-5% wrong and must never refuse service."""
    await build_menu_price(
        db_session,
        website_api.tenant_id,
        website_api.price_list_id,
        website_api.kitchen.dishes["STEAK"],
        "32.00",
    )
    response = await website_api.client.post(
        ORDERS_URL,
        json=_order(website_api.kitchen.dishes["STEAK"]),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == OrderTicketStatus.SENT_TO_KITCHEN.value
