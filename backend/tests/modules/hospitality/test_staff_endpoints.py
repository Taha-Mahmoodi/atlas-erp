"""Hospitality STAFF HTTP behaviour (PLAN 19 Task 6): the ticket lifecycle over the wire, the 86
endpoints, RBAC, tenant isolation, D-013 replay of a fire, and the derived at-risk list.

The at-risk tests are the point of the task. Q2 rejects DERIVED availability for the guest-facing
answer, and this endpoint is the one place the recipe math is allowed back in — advisory, staff-only
and computed from ON-HAND ONLY. Two tests pin exactly that: the query count must not grow with the
menu (Q2 measured the naive shape at ~1,080 queries for 60 items), and an open purchase order must
not raise a dish's producible count the way ``atp_check``'s ``on_hand - committed + on_order``
formula would.
"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import Job, wait_for_jobs
from app.core.rbac import catalog_keys
from app.core.tenancy import tenant_context
from app.modules.procurement import queries as procurement_queries
from app.modules.procurement import service as procurement_service
from app.modules.procurement.constants import ApprovalDocumentType
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.hospitality.conftest import HospitalityApi
from tests.modules.hospitality.factories import HospitalityPrincipal, build_dish
from tests.modules.procurement.factories import (
    build_approval_rule,
    build_approved_item,
    build_po,
    build_vendor,
    seed_currency,
)

AT_RISK_URL = "/api/v1/hospitality/menu/at-risk"


async def _open_ticket(api: HospitalityApi, *, quantity: str = "1") -> dict:
    response = await api.client.post(
        "/api/v1/hospitality/tickets",
        json={
            "table_code": "T12",
            "guest_count": 2,
            "lines": [
                {
                    "item_id": str(api.kitchen.dishes["PASTA"]),
                    "quantity": quantity,
                    "unit_price": "18.50",
                }
            ],
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- The ticket lifecycle over the wire ---------------------------------------


async def test_open_a_check_over_the_wire(hospitality_api: HospitalityApi) -> None:
    """POST /tickets opens an OPEN check with a gapless TKT- number and the maintained total."""
    ticket = await _open_ticket(hospitality_api, quantity="2")
    assert ticket["status"] == "OPEN"
    assert ticket["ticket_number"].startswith("TKT-")
    # D-015: money crosses the wire as a decimal STRING, never a float.
    assert ticket["total_amount"] == "37.000000"
    assert isinstance(ticket["total_amount"], str)


async def test_ticket_lines_read_back(hospitality_api: HospitalityApi) -> None:
    ticket = await _open_ticket(hospitality_api)
    response = await hospitality_api.client.get(
        f"/api/v1/hospitality/tickets/{ticket['id']}/lines"
    )
    assert response.status_code == 200, response.text
    lines = response.json()
    assert len(lines) == 1
    assert lines[0]["line_number"] == 1
    assert lines[0]["item_id"] == str(hospitality_api.kitchen.dishes["PASTA"])


async def test_fire_then_advance_then_settle(hospitality_api: HospitalityApi) -> None:
    """The whole floor lifecycle: fire → IN_PREP → READY → SERVED → settle."""
    ticket = await _open_ticket(hospitality_api)
    client = hospitality_api.client
    fired = await client.post(
        f"/api/v1/hospitality/tickets/{ticket['id']}/fire",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert fired.status_code == 200, fired.text
    assert fired.json()["status"] == "SENT_TO_KITCHEN"
    assert fired.json()["fired_at"] is not None
    await wait_for_jobs()  # the depletion job the fire scheduled, drained deterministically

    for status in ("IN_PREP", "READY", "SERVED"):
        moved = await client.post(
            f"/api/v1/hospitality/tickets/{ticket['id']}/advance", json={"status": status}
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["status"] == status

    settled = await client.post(f"/api/v1/hospitality/tickets/{ticket['id']}/settle")
    assert settled.status_code == 200, settled.text
    assert settled.json()["status"] == "SETTLED"
    assert settled.json()["settled_at"] is not None


async def test_firing_an_86d_dish_is_refused(hospitality_api: HospitalityApi) -> None:
    """Q2's whole point at the terminal: hiding a dish on the website is not enough, because a
    server's terminal never read the website."""
    client = hospitality_api.client
    dish_id = hospitality_api.kitchen.dishes["PASTA"]
    eighty_sixed = await client.put(
        f"/api/v1/hospitality/menu/{dish_id}/availability",
        json={"state": "EIGHTY_SIXED", "reason": "out of basil"},
    )
    assert eighty_sixed.status_code == 200, eighty_sixed.text
    assert eighty_sixed.json()["state"] == "EIGHTY_SIXED"

    ticket = await _open_ticket(hospitality_api)
    refused = await client.post(
        f"/api/v1/hospitality/tickets/{ticket['id']}/fire",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "hospitality.item_unavailable"

    cleared = await client.delete(f"/api/v1/hospitality/menu/{dish_id}/availability")
    assert cleared.status_code == 204, cleared.text
    fired = await client.post(
        f"/api/v1/hospitality/tickets/{ticket['id']}/fire",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert fired.status_code == 200, fired.text
    await wait_for_jobs()


async def test_a_replayed_fire_does_not_fire_the_kitchen_twice(
    hospitality_api: HospitalityApi, db_session: AsyncSession
) -> None:
    """D-013: a terminal retrying a timed-out fire must not submit a second depletion job — the
    guest's ingredients would leave the storeroom twice."""
    ticket = await _open_ticket(hospitality_api)
    key = uuid.uuid4().hex
    url = f"/api/v1/hospitality/tickets/{ticket['id']}/fire"
    first = await hospitality_api.client.post(url, headers={"Idempotency-Key": key})
    second = await hospitality_api.client.post(url, headers={"Idempotency-Key": key})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    await wait_for_jobs()

    with tenant_context(hospitality_api.tenant_id):
        jobs = (
            await db_session.execute(
                select(func.count(Job.id)).where(Job.tenant_id == hospitality_api.tenant_id)
            )
        ).scalar_one()
    assert jobs == 1


async def test_ticket_list_filters_by_status(hospitality_api: HospitalityApi) -> None:
    ticket = await _open_ticket(hospitality_api)
    await hospitality_api.client.post(
        f"/api/v1/hospitality/tickets/{ticket['id']}/fire",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    await wait_for_jobs()
    open_page = await hospitality_api.client.get(
        "/api/v1/hospitality/tickets", params={"status": "OPEN"}
    )
    fired_page = await hospitality_api.client.get(
        "/api/v1/hospitality/tickets", params={"status": "SENT_TO_KITCHEN"}
    )
    assert open_page.json()["items"] == []
    assert [item["id"] for item in fired_page.json()["items"]] == [ticket["id"]]


async def test_ticket_list_is_within_the_query_budget(
    hospitality_api: HospitalityApi, query_counter: Callable[[], QueryCounter]
) -> None:
    """PERFORMANCE §2: a list endpoint runs O(1) queries."""
    await _open_ticket(hospitality_api)
    await assert_query_budget(
        hospitality_api.client, query_counter, "/api/v1/hospitality/tickets"
    )


# --- RBAC + tenancy -----------------------------------------------------------


async def test_a_server_without_the_settle_key_cannot_settle(
    hospitality_api: HospitalityApi,
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """``ticket.settle`` is a separate key from ``ticket.manage`` so a server can run the floor
    without being able to close out a check."""
    ticket = await _open_ticket(hospitality_api)
    without_settle = tuple(
        key
        for key in sorted(catalog_keys())
        if key.startswith("hospitality.") and key != "hospitality.ticket.settle"
    )
    principal = await hospitality_user_factory(
        slug="hsp-floor", email="server@hsp-floor.test", keys=without_settle
    )
    transport = client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as floor:
        token = (
            await floor.post(
                "/api/v1/auth/login",
                json={
                    "tenant_slug": principal.tenant_slug,
                    "email": principal.email,
                    "password": principal.password,
                },
            )
        ).json()["access_token"]
        floor.headers["Authorization"] = f"Bearer {token}"
        denied = await floor.post(f"/api/v1/hospitality/tickets/{ticket['id']}/settle")
    assert denied.status_code == 403, denied.text


async def test_another_tenants_ticket_is_not_readable(
    hospitality_api: HospitalityApi,
    client: AsyncClient,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> None:
    """D-007: a second property cannot read the first's checks, even with the right key."""
    ticket = await _open_ticket(hospitality_api)
    principal = await hospitality_user_factory(slug="hsp-beta", email="chef@hsp-beta.test")
    transport = client._transport
    async with AsyncClient(transport=transport, base_url="https://test") as other:
        token = (
            await other.post(
                "/api/v1/auth/login",
                json={
                    "tenant_slug": principal.tenant_slug,
                    "email": principal.email,
                    "password": principal.password,
                },
            )
        ).json()["access_token"]
        other.headers["Authorization"] = f"Bearer {token}"
        response = await other.get(f"/api/v1/hospitality/tickets/{ticket['id']}")
    assert response.status_code == 404, response.text


# --- The derived at-risk list -------------------------------------------------


async def test_at_risk_reports_max_producible_and_the_limiting_ingredient(
    hospitality_api: HospitalityApi,
) -> None:
    """The advisory number a human 86s from: "feta covers 2 more portions". No ``threshold``
    parameter, so this also pins ``AT_RISK_DEFAULT_THRESHOLD`` (5) as the default a caller who does
    not care gets."""
    kitchen = hospitality_api.kitchen
    response = await hospitality_api.client.get(AT_RISK_URL)
    assert response.status_code == 200, response.text
    rows = {row["item_id"]: row for row in response.json()}

    steak = rows[str(kitchen.dishes["STEAK"])]
    assert steak["max_producible"] == 0
    assert steak["limiting_item_id"] == str(kitchen.ingredients["BEEF"])

    pasta = rows[str(kitchen.dishes["PASTA"])]
    assert pasta["max_producible"] == 5  # 10 tomato / 2 per portion, the tighter of the two
    assert pasta["limiting_item_id"] == str(kitchen.ingredients["TOMATO"])

    # Worst first, so a truncated page is the useful end of the list.
    assert [row["item_id"] for row in response.json()][0] == str(kitchen.dishes["STEAK"])
    # A dish with no recipe has nothing to explode and is never on the list.
    assert str(kitchen.dishes["BEER"]) not in rows


async def test_at_risk_threshold_narrows_the_list(hospitality_api: HospitalityApi) -> None:
    response = await hospitality_api.client.get(AT_RISK_URL, params={"threshold": 0})
    assert response.status_code == 200, response.text
    assert [row["item_id"] for row in response.json()] == [
        str(hospitality_api.kitchen.dishes["STEAK"])
    ]


async def test_at_risk_query_count_does_not_grow_with_the_menu(
    hospitality_api: HospitalityApi,
    db_session: AsyncSession,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """Q2's 360x finding, pinned. The naive per-item shape (``atp_check`` is 3 queries per item)
    costs ~1,080 queries for a 60-item menu; this endpoint's cost must be flat in menu size.
    """
    client = hospitality_api.client
    url = f"{AT_RISK_URL}?threshold=1000000&limit=200"
    await client.get(url)  # warm the D-009 RBAC TTL cache
    with query_counter() as small:
        first = await client.get(url)
    assert first.status_code == 200, first.text

    tomato = hospitality_api.kitchen.ingredients["TOMATO"]
    for index in range(20):
        await build_dish(
            db_session,
            hospitality_api.tenant_id,
            hospitality_api.kitchen.setup,
            item_code=f"EXTRA-{index:02d}",
            recipe={tomato: Decimal(1)},
        )

    with query_counter() as large:
        second = await client.get(url)
    assert second.status_code == 200, second.text
    assert len(second.json()) == len(first.json()) + 20
    assert large.count == small.count, (
        f"the at-risk list cost {small.count} queries for a 2-dish menu and {large.count} for a "
        f"22-dish one — it must be flat in menu size:\n" + "\n".join(large.statements)
    )
    assert large.count <= 3  # PERFORMANCE §2


async def test_at_risk_uses_on_hand_only_not_on_order(
    hospitality_api: HospitalityApi, db_session: AsyncSession
) -> None:
    """The Q2 formula bug, pinned: ``atp_check`` is ``on_hand - committed + on_order``, so an open
    PO for beef would make tonight's steak read producible. A kitchen cannot cook a purchase order.
    """
    kitchen = hospitality_api.kitchen
    beef_id = kitchen.ingredients["BEEF"]
    tenant_id = hospitality_api.tenant_id

    before = await hospitality_api.client.get(AT_RISK_URL, params={"threshold": 10})
    assert next(
        row for row in before.json() if row["item_id"] == str(kitchen.dishes["STEAK"])
    )["max_producible"] == 0

    await seed_currency(db_session, tenant_id)
    await build_approval_rule(
        db_session,
        tenant_id,
        document_type=ApprovalDocumentType.PURCHASE_ORDER,
        threshold_amount="100000",
    )
    vendor = await build_vendor(db_session, tenant_id)
    await build_approved_item(db_session, tenant_id, vendor.id, beef_id)
    po = await build_po(
        db_session,
        tenant_id,
        vendor_id=vendor.id,
        item_id=beef_id,
        uom_id=kitchen.setup.base_uom_id,
        quantity="500",
        unit_cost="5",
    )
    with tenant_context(tenant_id):
        sent = await procurement_service.send_purchase_order(db_session, tenant_id, po.id)
        await db_session.commit()
        on_order = await procurement_queries.open_incoming_quantity(
            db_session, tenant_id, beef_id
        )
    # The PO really is on-order, so the assertion below is not vacuous.
    assert sent.status == "SENT"
    assert on_order == Decimal(500)

    after = await hospitality_api.client.get(AT_RISK_URL, params={"threshold": 10})
    steak = next(row for row in after.json() if row["item_id"] == str(kitchen.dishes["STEAK"]))
    assert steak["max_producible"] == 0, "an open PO must not make a dish read producible"
