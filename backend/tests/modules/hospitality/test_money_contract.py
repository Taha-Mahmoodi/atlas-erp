"""Adversarial money-and-contract tests for the hospitality surface (PLAN 19).

Three questions, asked of the shipped code rather than of the plan:

1. **Is every monetary value a decimal STRING (D-015)?** Not just the two fields the Task 7 tests
   already spot-check — every field of every hospitality response, including the replayed body a
   D-013 retry re-emits from storage and the error body of a refused order. The sweep is done by
   re-parsing the raw response text with ``parse_float`` wired to explode, so a float ANYWHERE in
   the payload fails the test regardless of which field grew it.
2. **Is the order response's total authoritative (Q6)?** The menu is cached for 60 s, so the only
   interesting case is the one the cache window creates: the price changed AFTER the website read
   the menu. The response must carry Atlas's number, and the lines of a check must sum to it
   exactly — a header total that is not Σ lines is a check that cannot be explained to a guest.
3. **Does the 86 board fit ONE page?** ``MenuAvailabilityPage`` documents "everything absent is
   available" as the contract, which turns a SILENTLY TRUNCATED page into "these sold-out dishes
   are available". ``as_of`` only describes one snapshot, so a board that spans two pages has no
   single instant to report either.

Plus one scope audit: the plan's "Explicitly not in Phase 19" list, asserted against the actual
route table rather than against the docstrings that claim it.
"""

import json
import uuid
from decimal import Decimal
from typing import Any

from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import DEFAULT_LIMIT
from app.core.tenancy import tenant_context
from app.modules.hospitality import router as staff_router_module
from app.modules.hospitality import schemas as hospitality_schemas
from app.modules.hospitality import website_router as website_router_module
from app.modules.hospitality.constants import AvailabilityState
from app.modules.hospitality.models import MenuAvailability
from app.modules.hospitality.service import availability
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import PriceListItemCreate
from tests.modules.hospitality.conftest import MENU_PRICES, HospitalityApi, WebsiteApi

MENU_URL = "/api/v1/hospitality/menu"
AVAILABILITY_URL = "/api/v1/hospitality/menu/availability"
ORDERS_URL = "/api/v1/hospitality/orders"
TICKETS_URL = "/api/v1/hospitality/tickets"


def _no_floats(raw: str) -> float:
    raise AssertionError(f"a JSON number with a decimal point crossed the wire: {raw!r}")


def assert_no_floats(response: Response) -> Any:
    """Re-parse the RAW body with ``parse_float`` wired to explode (D-015).

    Asserting ``isinstance(body["total_amount"], str)`` only guards the field the test names; this
    guards the whole document, so a new money field serialized as a float fails here whatever it is
    called. Integers still parse (``line_number``, ``guest_count``, ``limit``) — the rule is about
    fractional numbers, and every fractional value in this module is money or a quantity.
    """
    return json.loads(response.text, parse_float=_no_floats)


async def _reprice(
    session: AsyncSession, api: WebsiteApi, item_id: uuid.UUID, unit_price: str
) -> None:
    """The chef changes a menu price — remove the list price and set the new one (sales has no
    in-place update; a price-list item is config, so removal is a real delete)."""
    with tenant_context(api.tenant_id):
        await sales_service.remove_price_list_item(
            session, api.tenant_id, api.price_list_id, item_id
        )
        await sales_service.add_price_list_item(
            session,
            api.tenant_id,
            api.price_list_id,
            PriceListItemCreate(item_id=item_id, unit_price=Decimal(unit_price)),
        )
        await session.commit()


# --- D-015: money is a decimal string, everywhere ------------------------------


async def test_no_hospitality_response_carries_a_float(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The whole website surface in one sweep: the menu read, the 86 board, the order write and
    the body a D-013 replay re-emits from ``core_idempotency_keys``.

    The replay is the one worth naming. It does not run the handler — the stored body is returned
    verbatim — so it is serialized by a completely different code path from the first response, and
    a total stored as a float would only ever surface on a retry.
    """
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            website_api.kitchen.dishes["BEER"],
            state=AvailabilityState.LIMITED,
            remaining_qty=Decimal("2.5"),
        )
        await db_session.commit()

    menu = await website_api.client.get(MENU_URL)
    assert menu.status_code == 200, menu.text
    assert_no_floats(menu)
    priced = {row["item_code"]: row["price"] for row in menu.json()["items"]}
    assert isinstance(priced["PASTA"], str)

    board = await website_api.client.get(AVAILABILITY_URL)
    assert board.status_code == 200, board.text
    assert_no_floats(board)
    counted = [row for row in board.json()["items"] if row["remaining_qty"] is not None]
    assert counted and all(isinstance(row["remaining_qty"], str) for row in counted)

    key = uuid.uuid4().hex
    body = {"lines": [{"item_id": str(website_api.kitchen.dishes["PASTA"]), "quantity": "3"}]}
    first = await website_api.client.post(ORDERS_URL, json=body, headers={"Idempotency-Key": key})
    assert first.status_code == 201, first.text
    assert_no_floats(first)

    replay = await website_api.client.post(ORDERS_URL, json=body, headers={"Idempotency-Key": key})
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert_no_floats(replay)
    assert replay.json() == first.json(), "a replay must re-emit the first body byte-identically"


async def test_no_staff_ticket_response_carries_a_float(hospitality_api: HospitalityApi) -> None:
    """The staff side of D-015: the ticket read, its lines, and every lifecycle response."""
    client = hospitality_api.client
    created = await client.post(
        TICKETS_URL,
        json={
            "table_code": "T4",
            "lines": [
                {
                    "item_id": str(hospitality_api.kitchen.dishes["PASTA"]),
                    "quantity": "1.5",
                    "unit_price": "18.50",
                },
                {
                    "item_id": str(hospitality_api.kitchen.dishes["BEER"]),
                    "quantity": "3",
                    "unit_price": "6.25",
                },
            ],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert created.status_code == 201, created.text
    assert_no_floats(created)
    ticket_id = created.json()["id"]

    read = await client.get(f"{TICKETS_URL}/{ticket_id}")
    assert_no_floats(read)
    assert isinstance(read.json()["total_amount"], str)

    lines = await client.get(f"{TICKETS_URL}/{ticket_id}/lines")
    assert_no_floats(lines)
    for line in lines.json():
        assert isinstance(line["unit_price"], str)
        assert isinstance(line["line_amount"], str)
        assert isinstance(line["quantity"], str)

    listed = await client.get(TICKETS_URL)
    assert_no_floats(listed)


def test_the_published_schema_types_every_money_field_as_a_string() -> None:
    """D-015 in the CONTRACT, not just in one response.

    A generated client is written against ``openapi.json``, so a money field typed ``number`` there
    puts the price in a float in every consumer of the API even while the server happens to send a
    string. FastAPI renders response models in SERIALIZATION mode, which is what makes ``Decimal``
    come out as ``string`` — a hand-rolled ``float`` annotation would come out as ``number`` and is
    exactly what this catches.

    RESPONSE shapes only. A request body is published in VALIDATION mode, where ``Decimal`` renders
    as ``anyOf[string, number]`` — leniency on the way IN, which D-015 does not govern (and the
    website's order body carries no money at all).
    """
    from app.main import create_app

    schemas = create_app().openapi()["components"]["schemas"]
    money_fields = ("price", "total_amount", "unit_price", "line_amount", "remaining_qty")
    checked = 0
    for name in hospitality_schemas.__all__:
        if not name.endswith(("Read", "Page")):
            continue
        for field, declared in schemas.get(name, {}).get("properties", {}).items():
            if field not in money_fields:
                continue
            # Optional fields render as anyOf[<type>, null]; unwrap before asserting.
            variants = declared.get("anyOf", [declared])
            types = {variant.get("type") for variant in variants} - {"null"}
            assert types == {"string"}, f"{name}.{field} is published as {types}, not string"
            checked += 1
    assert checked >= len(money_fields), "the sweep found no money fields — the names drifted"


async def test_a_refused_order_returns_an_error_body_with_no_float(
    website_api: WebsiteApi,
) -> None:
    """An error body is a wire payload too. A refusal that quoted a price as a float would be a
    D-015 breach in the one response nobody schema-checks, and a Decimal left in ``details`` would
    not even serialize — ``_error_response`` dumps in PYTHON mode into a plain ``JSONResponse``."""
    refused = await website_api.client.post(
        ORDERS_URL,
        json={
            "lines": [
                {"item_id": str(website_api.kitchen.ingredients["TOMATO"]), "quantity": "1"}
            ]
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert refused.status_code == 422, refused.text
    assert_no_floats(refused)
    assert refused.json()["error"]["code"] == "hospitality.item_not_priced"


# --- Q6: the response total is authoritative -----------------------------------


async def test_the_order_total_is_atlas_price_not_the_websites_cached_one(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """The exact hazard ``max-age=60`` creates. The website reads the menu at 18.50, the chef
    reprices to 25.00, and a guest orders from the page they are still looking at.

    Atlas must strike the check at ITS price and say so in the response — that is what makes
    "display the total we return, never the one you computed" (Q6) a rule the website can follow.
    """
    dish_id = website_api.kitchen.dishes["PASTA"]
    cached = await website_api.client.get(MENU_URL)
    cached_price = Decimal(
        next(row["price"] for row in cached.json()["items"] if row["item_code"] == "PASTA")
    )
    assert cached_price == MENU_PRICES["PASTA"]

    await _reprice(db_session, website_api, dish_id, "25.00")

    order = await website_api.client.post(
        ORDERS_URL,
        json={"lines": [{"item_id": str(dish_id), "quantity": "2"}]},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert order.status_code == 201, order.text
    total = Decimal(order.json()["total_amount"])
    assert total == Decimal("50.00"), "the check must be struck at Atlas's CURRENT price"
    assert total != cached_price * 2, "the response echoed the price the website had cached"


async def test_the_lines_of_a_check_sum_to_its_total(hospitality_api: HospitalityApi) -> None:
    """Σ line_amount == total_amount, read back from the DATABASE rather than from the numbers the
    service happened to hold in memory.

    The prices are deliberately awkward: a fractional quantity and a unit price carrying more
    decimals than the currency, which is where a per-line rounding and a whole-total rounding come
    apart. A guest can be shown either number; they must not be two numbers.
    """
    client = hospitality_api.client
    created = await client.post(
        TICKETS_URL,
        json={
            "lines": [
                {
                    "item_id": str(hospitality_api.kitchen.dishes["PASTA"]),
                    "quantity": "3",
                    "unit_price": "0.3333335",
                },
                {
                    "item_id": str(hospitality_api.kitchen.dishes["BEER"]),
                    "quantity": "3",
                    "unit_price": "0.3333335",
                },
                {
                    "item_id": str(hospitality_api.kitchen.dishes["STEAK"]),
                    "quantity": "1.5",
                    "unit_price": "19.99",
                },
            ]
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert created.status_code == 201, created.text
    ticket_id = created.json()["id"]

    lines = (await client.get(f"{TICKETS_URL}/{ticket_id}/lines")).json()
    stored_total = Decimal((await client.get(f"{TICKETS_URL}/{ticket_id}")).json()["total_amount"])
    line_sum = sum((Decimal(line["line_amount"]) for line in lines), Decimal(0))
    assert line_sum == stored_total, (
        f"the check's lines sum to {line_sum} but its total reads {stored_total} — a guest "
        "reading the itemisation and a guest reading the bottom line see different money"
    )

    added = await client.post(
        f"{TICKETS_URL}/{ticket_id}/lines",
        json={
            "lines": [
                {
                    "item_id": str(hospitality_api.kitchen.dishes["PASTA"]),
                    "quantity": "1",
                    "unit_price": "0.3333335",
                }
            ]
        },
    )
    assert added.status_code == 200, added.text
    lines = (await client.get(f"{TICKETS_URL}/{ticket_id}/lines")).json()
    line_sum = sum((Decimal(line["line_amount"]) for line in lines), Decimal(0))
    assert line_sum == Decimal(added.json()["total_amount"]), (
        "adding a course broke Σ lines == total"
    )


# --- Q6: the 86 board is ONE page ----------------------------------------------


async def test_the_86_board_serves_every_override_on_one_page(
    website_api: WebsiteApi, db_session: AsyncSession
) -> None:
    """``MenuAvailabilityPage`` contracts that availability FITS ONE PAGE and that everything
    ABSENT from it is available. Those two clauses only hold together if the endpoint actually
    serves the whole board: a page truncated at the D-014 default of 50 tells a website that every
    override past the fiftieth is available, which is a sold-out dish sold.

    ``as_of`` has the same dependency — it names ONE instant, and there is no single instant for a
    board the client had to stitch out of two requests.
    """
    board = website_api.kitchen.dishes["PASTA"]
    with tenant_context(website_api.tenant_id):
        await availability.set_availability(
            db_session,
            website_api.tenant_id,
            board,
            state=AvailabilityState.EIGHTY_SIXED,
            reason="out of basil",
        )
        # Filler overrides with low ids so the real 86 sorts LAST under the item_id ordering: this
        # is a property mid-service with a counter on most of its menu, which is exactly the size
        # the plan's MAX_LIMIT envelope allows and the DEFAULT_LIMIT page silently cuts.
        for index in range(DEFAULT_LIMIT + 5):
            db_session.add(
                MenuAvailability(
                    tenant_id=website_api.tenant_id,
                    item_id=uuid.UUID(int=index + 1),
                    state=AvailabilityState.LIMITED.value,
                    remaining_qty=Decimal(3),
                )
            )
        await db_session.commit()

    response = await website_api.client.get(AVAILABILITY_URL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["as_of"] is not None
    assert body["next_cursor"] is None, (
        f"the 86 board spilled onto a second page ({len(body['items'])} rows served) — the "
        "contract that everything absent is AVAILABLE turns the tail into sold-out dishes on sale"
    )
    assert str(board) in {row["item_id"] for row in body["items"]}, (
        "the 86'd dish fell off the served page; a website reading this board would sell it"
    )


# --- The plan's "Explicitly not in Phase 19" list ------------------------------

# Every route the two hospitality routers may expose. A route added here that is NOT on this list
# fails the test, which is the point: the plan's exclusion list (modifier-level 86, day-part menus,
# delivery injection, KDS hardware, online card payment, the room-charge bridge) is only worth
# anything if something checks the surface instead of the docstrings.
EXPECTED_ROUTES = {
    ("GET", "/api/v1/hospitality/menu/at-risk"),
    ("PUT", "/api/v1/hospitality/menu/{item_id}/availability"),
    ("DELETE", "/api/v1/hospitality/menu/{item_id}/availability"),
    ("POST", "/api/v1/hospitality/tickets"),
    ("GET", "/api/v1/hospitality/tickets"),
    ("GET", "/api/v1/hospitality/tickets/{ticket_id}"),
    ("GET", "/api/v1/hospitality/tickets/{ticket_id}/lines"),
    ("POST", "/api/v1/hospitality/tickets/{ticket_id}/lines"),
    ("POST", "/api/v1/hospitality/tickets/{ticket_id}/fire"),
    ("POST", "/api/v1/hospitality/tickets/{ticket_id}/advance"),
    ("POST", "/api/v1/hospitality/tickets/{ticket_id}/settle"),
    ("GET", "/api/v1/hospitality/menu"),
    ("GET", "/api/v1/hospitality/menu/availability"),
    ("POST", "/api/v1/hospitality/orders"),
}

# Words from the exclusion list. A field carrying one of these is scope that was meant to wait.
OUT_OF_SCOPE_FIELD_WORDS = (
    "modifier",
    "day_part",
    "daypart",
    "delivery",
    "kds",
    "prep_station",
    "payment",
    "card",
    "folio",
    "room_",
    "split",
)


def test_the_hospitality_route_table_is_exactly_phase_19() -> None:
    routes = {
        (method, route.path)
        for module in (staff_router_module, website_router_module)
        for route in module.router.routes
        for method in getattr(route, "methods", set())
        if method != "HEAD"
    }
    assert routes == EXPECTED_ROUTES, (
        f"unexpected: {sorted(routes - EXPECTED_ROUTES)}; missing: "
        f"{sorted(EXPECTED_ROUTES - routes)}"
    )


def test_no_hospitality_wire_field_names_out_of_scope_work() -> None:
    """The exclusion list again, one level down: a route can stay put while a field smuggles the
    feature in (a ``payment_method`` on the order, a ``modifiers`` array on a line)."""
    offenders = {
        f"{name}.{field}"
        for name in hospitality_schemas.__all__
        for field in getattr(hospitality_schemas, name).model_fields
        for word in OUT_OF_SCOPE_FIELD_WORDS
        if word in field.lower()
    }
    assert not offenders, f"out-of-scope wire fields: {sorted(offenders)}"
