"""Production-order HTTP tests (PLAN 8.2, D-048): create+explode, release, issue, finish, the
WIP-nets-to-zero proof over the wire, idempotency, RBAC, budget, docflow chain, isolation.

Drives the endpoints against a fully-wired tenant (the ``production_api`` fixture seeds items + GL
accounts + open period + warehouse/bins + WIP/variance defaults + component on-hand + an ACTIVE BOM
in the client's tenant). The WIP-nets-to-zero proof reads the trial balance via the account-balances
aggregate. RBAC + isolation reuse the manufacturing principal pattern.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import queries as finance_queries
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.manufacturing.conftest import ProductionApi

pytestmark = pytest.mark.asyncio

_MFG = "/api/v1/manufacturing"


def _idem() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def _create_order(api: ProductionApi, *, quantity: str = "5") -> dict:
    resp = await api.client.post(
        f"{_MFG}/production-orders",
        json={
            "item_id": str(api.setup.parent_item_id),
            "quantity": quantity,
            "warehouse_id": str(api.setup.warehouse_id),
        },
        headers=_idem(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- create + explode ---------------------------------------------------------


async def test_create_explodes_and_numbers(production_api: ProductionApi) -> None:
    order = await _create_order(production_api, quantity="5")
    assert order["status"] == "DRAFT"
    assert order["order_number"].startswith("MO")
    # qty_per default 2 × order 5 = 10 required (no scrap in the default setup).
    assert len(order["components"]) == 1
    assert Decimal(order["components"][0]["required_quantity"]) == Decimal(10)
    assert Decimal(order["components"][0]["issued_quantity"]) == 0


async def test_create_no_active_bom_is_422(production_api: ProductionApi) -> None:
    """Ordering the COMPONENT item (which has no BOM) → 422 manufacturing.no_active_bom."""
    resp = await production_api.client.post(
        f"{_MFG}/production-orders",
        json={
            "item_id": str(production_api.setup.component_item_id),
            "quantity": "1",
            "warehouse_id": str(production_api.setup.warehouse_id),
        },
        headers=_idem(),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "manufacturing.no_active_bom"


# --- full flow over the wire + WIP nets to zero -------------------------------


async def test_full_flow_over_the_wire_wip_nets_to_zero(
    production_api: ProductionApi, db_session: AsyncSession
) -> None:
    api = production_api
    order = await _create_order(api, quantity="5")
    order_id = order["id"]

    released = await api.client.post(f"{_MFG}/production-orders/{order_id}/release")
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"

    issued = await api.client.post(
        f"{_MFG}/production-orders/{order_id}/issue-components", json={}, headers=_idem()
    )
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["status"] == "IN_PROGRESS"
    assert Decimal(body["accumulated_wip_cost"]) == Decimal(30)  # 10 units × $3
    assert Decimal(body["components"][0]["issued_quantity"]) == Decimal(10)

    finished = await api.client.post(
        f"{_MFG}/production-orders/{order_id}/finish",
        json={"finished_quantity": "5", "finished_bin_id": str(api.setup.finished_bin_id)},
        headers=_idem(),
    )
    assert finished.status_code == 200, finished.text
    fbody = finished.json()
    assert fbody["status"] == "FINISHED"
    assert Decimal(fbody["finished_quantity"]) == Decimal(5)
    assert Decimal(fbody["accumulated_wip_cost"]) == 0

    # WIP nets to ZERO over the trial balance (the journal posted through the event bus).
    with tenant_context(api.setup.tenant_id):
        balances = await finance_queries.account_balances(
            db_session, api.setup.tenant_id, date_to=date(2099, 1, 1)
        )
    assert balances.get(api.setup.wip_account_id, Decimal(0)) == Decimal(0)


# --- idempotency --------------------------------------------------------------


async def test_create_is_idempotent(production_api: ProductionApi) -> None:
    api = production_api
    key = _idem()
    payload = {
        "item_id": str(api.setup.parent_item_id),
        "quantity": "5",
        "warehouse_id": str(api.setup.warehouse_id),
    }
    first = await api.client.post(f"{_MFG}/production-orders", json=payload, headers=key)
    second = await api.client.post(f"{_MFG}/production-orders", json=payload, headers=key)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["order_number"] == second.json()["order_number"]


async def test_issue_is_idempotent(production_api: ProductionApi) -> None:
    api = production_api
    order = await _create_order(api, quantity="5")
    order_id = order["id"]
    await api.client.post(f"{_MFG}/production-orders/{order_id}/release")
    key = _idem()
    first = await api.client.post(
        f"{_MFG}/production-orders/{order_id}/issue-components", json={}, headers=key
    )
    second = await api.client.post(
        f"{_MFG}/production-orders/{order_id}/issue-components", json={}, headers=key
    )
    assert first.status_code == 200
    assert second.status_code == 200
    # The replay returns the captured response — issued quantity is NOT doubled.
    assert Decimal(first.json()["accumulated_wip_cost"]) == Decimal(30)
    assert Decimal(second.json()["accumulated_wip_cost"]) == Decimal(30)


# --- list + budget ------------------------------------------------------------


async def test_list_filters_and_budget(
    production_api: ProductionApi, query_counter: Callable[[], QueryCounter]
) -> None:
    api = production_api
    for _ in range(3):
        await _create_order(api, quantity="5")
    listed = await api.client.get(f"{_MFG}/production-orders?status=DRAFT")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 3
    await assert_query_budget(
        api.client, query_counter, f"{_MFG}/production-orders?status=DRAFT", budget=3
    )


# --- docflow chain ------------------------------------------------------------


async def test_docflow_links_order_to_moves(
    production_api: ProductionApi, db_session: AsyncSession
) -> None:
    """After issue + finish the docflow chain links the order document to the component-issue moves
    ('issued_to') and the finished-receipt move ('finished_to')."""
    api = production_api
    order = await _create_order(api, quantity="5")
    order_id = order["id"]
    await api.client.post(f"{_MFG}/production-orders/{order_id}/release")
    await api.client.post(
        f"{_MFG}/production-orders/{order_id}/issue-components", json={}, headers=_idem()
    )
    await api.client.post(
        f"{_MFG}/production-orders/{order_id}/finish",
        json={"finished_quantity": "5", "finished_bin_id": str(api.setup.finished_bin_id)},
        headers=_idem(),
    )
    # The chain endpoint is keyed by the order's core_documents id; resolve it from the order row.
    from app.modules.manufacturing.models import ProductionOrder

    with tenant_context(api.setup.tenant_id):
        document_id = (
            await db_session.get(ProductionOrder, uuid.UUID(order_id))
        ).document_id
    chain = await api.client.get(f"/api/v1/documents/{document_id}/chain")
    assert chain.status_code == 200, chain.text
    link_types = {edge["link_type"] for edge in chain.json()["edges"]}
    assert "issued_to" in link_types
    assert "finished_to" in link_types


# --- RBAC ---------------------------------------------------------------------


async def test_execute_requires_permission(
    client: AsyncClient, mfg_user_factory: Callable[..., object]
) -> None:
    """A principal with only .read/.manage cannot issue components (403) — issue/finish need
    .execute."""
    principal = await mfg_user_factory(
        slug="mfg-noexec",
        email="noexec@mfg.test",
        keys=(
            "manufacturing.production_order.read",
            "manufacturing.production_order.manage",
        ),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    resp = await client.post(
        f"{_MFG}/production-orders/{uuid.uuid4()}/issue-components", json={}, headers=_idem()
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


# --- isolation ----------------------------------------------------------------


async def test_other_tenant_cannot_read_order(
    production_api: ProductionApi, mfg_client_b: AsyncClient
) -> None:
    order = await _create_order(production_api, quantity="5")
    other = await mfg_client_b.get(f"{_MFG}/production-orders/{order['id']}")
    assert other.status_code == 404
