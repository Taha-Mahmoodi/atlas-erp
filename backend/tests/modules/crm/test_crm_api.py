"""CRM HTTP behaviour (PLAN 12.1, D-057): lead / opportunity / activity endpoints over the wire,
RBAC
(read vs manage vs convert), pagination, the ≤3-query list budgets (PERFORMANCE §6), the kanban
board
endpoint, the convert-to-customer+quote endpoint, and tenant isolation.

Driven against a real bearer-token client whose tenant has a seeded currency + item + customer +
employee.
"""

from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.crm.conftest import CrmApi

_CRM = "/api/v1/crm"


# --- Lead endpoints -----------------------------------------------------------


async def test_create_and_get_lead(crm_client: AsyncClient) -> None:
    create = await crm_client.post(
        f"{_CRM}/leads", json={"company_name": "API Co", "source": "web"}
    )
    assert create.status_code == 201, create.text
    lead_id = create.json()["id"]
    assert create.json()["status"] == "NEW"
    assert create.json()["lead_number"].startswith("LEAD-")
    got = await crm_client.get(f"{_CRM}/leads/{lead_id}")
    assert got.status_code == 200
    assert got.json()["company_name"] == "API Co"


async def test_lead_qualify_and_convert_over_the_wire(crm_api: CrmApi) -> None:
    create = await crm_api.client.post(
        f"{_CRM}/leads",
        json={"company_name": "Convert Co", "estimated_value": "1000", "currency_code": "USD"},
    )
    lead_id = create.json()["id"]
    qualify = await crm_api.client.post(f"{_CRM}/leads/{lead_id}/qualify")
    assert qualify.status_code == 200
    assert qualify.json()["status"] == "QUALIFIED"
    convert = await crm_api.client.post(f"{_CRM}/leads/{lead_id}/convert", json={})
    assert convert.status_code == 201, convert.text
    assert convert.json()["opportunity_number"].startswith("OPP-")
    assert convert.json()["source_lead_id"] == lead_id


async def test_lead_list_filtered_and_budget(
    crm_api: CrmApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await crm_api.client.post(f"{_CRM}/leads", json={"company_name": "L1"})
    await crm_api.client.post(f"{_CRM}/leads", json={"company_name": "L2"})
    await assert_query_budget(crm_api.client, query_counter, f"{_CRM}/leads")
    filtered = await crm_api.client.get(f"{_CRM}/leads", params={"status": "NEW"})
    assert filtered.status_code == 200
    assert len(filtered.json()["items"]) == 2


# --- Opportunity endpoints ----------------------------------------------------


async def test_create_opportunity_with_lines_over_the_wire(crm_api: CrmApi) -> None:
    create = await crm_api.client.post(
        f"{_CRM}/opportunities",
        json={
            "name": "API Deal",
            "company_name": "Prospect",
            "currency_code": "USD",
            "estimated_value": "5000",
            "lines": [
                {
                    "item_id": str(crm_api.setup.item_id),
                    "quantity": "2",
                    "estimated_unit_price": "250",
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["stage"] == "PROSPECTING"
    assert len(create.json()["lines"]) == 1


async def test_move_stage_over_the_wire(crm_api: CrmApi) -> None:
    create = await crm_api.client.post(
        f"{_CRM}/opportunities",
        json={"name": "D", "company_name": "P", "currency_code": "USD"},
    )
    opp_id = create.json()["id"]
    moved = await crm_api.client.post(
        f"{_CRM}/opportunities/{opp_id}/move-stage", json={"stage": "NEGOTIATION"}
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["stage"] == "NEGOTIATION"


async def test_kanban_board_endpoint(crm_api: CrmApi) -> None:
    """The kanban board returns a column per stage; a created opportunity lands in PROSPECTING."""
    await crm_api.client.post(
        f"{_CRM}/opportunities",
        json={"name": "D", "company_name": "P", "currency_code": "USD", "estimated_value": "400"},
    )
    board = await crm_api.client.get(f"{_CRM}/opportunities/kanban")
    assert board.status_code == 200, board.text
    columns = {col["stage"]: col for col in board.json()["columns"]}
    assert set(columns) == {
        "PROSPECTING",
        "QUALIFICATION",
        "PROPOSAL",
        "NEGOTIATION",
        "WON",
        "LOST",
    }
    assert columns["PROSPECTING"]["count"] == 1
    assert columns["PROSPECTING"]["total_estimated_value"] == "400.000000"


async def test_convert_opportunity_endpoint(crm_api: CrmApi) -> None:
    """THE convert endpoint: a prospect opportunity → WON with converted ids; a sales quote
    exists."""
    create = await crm_api.client.post(
        f"{_CRM}/opportunities",
        json={
            "name": "Win",
            "company_name": "Prospect",
            "currency_code": "USD",
            "lines": [
                {
                    "item_id": str(crm_api.setup.item_id),
                    "quantity": "4",
                    "estimated_unit_price": "25",
                }
            ],
        },
    )
    opp_id = create.json()["id"]
    convert = await crm_api.client.post(f"{_CRM}/opportunities/{opp_id}/convert", json={})
    assert convert.status_code == 200, convert.text
    body = convert.json()
    assert body["stage"] == "WON"
    assert body["converted_customer_id"] is not None
    assert body["converted_quote_id"] is not None


async def test_opportunity_list_budget(
    crm_api: CrmApi, query_counter: Callable[[], QueryCounter]
) -> None:
    await crm_api.client.post(
        f"{_CRM}/opportunities",
        json={"name": "D1", "company_name": "P", "currency_code": "USD"},
    )
    await assert_query_budget(crm_api.client, query_counter, f"{_CRM}/opportunities")


# --- Activity endpoints -------------------------------------------------------


async def test_activity_crud_and_complete_over_the_wire(crm_api: CrmApi) -> None:
    lead = await crm_api.client.post(f"{_CRM}/leads", json={"company_name": "Act Co"})
    lead_id = lead.json()["id"]
    create = await crm_api.client.post(
        f"{_CRM}/activities",
        json={"activity_type": "CALL", "subject": "Call", "lead_id": lead_id},
    )
    assert create.status_code == 201, create.text
    activity_id = create.json()["id"]
    assert create.json()["status"] == "OPEN"
    complete = await crm_api.client.post(f"{_CRM}/activities/{activity_id}/complete", json={})
    assert complete.status_code == 200
    assert complete.json()["status"] == "COMPLETED"
    assert complete.json()["completed_date"] is not None


async def test_activity_no_parent_422(crm_api: CrmApi) -> None:
    resp = await crm_api.client.post(
        f"{_CRM}/activities", json={"activity_type": "NOTE", "subject": "Orphan"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "crm.activity_parent_invalid"


async def test_activity_list_scoped_and_budget(
    crm_api: CrmApi, query_counter: Callable[[], QueryCounter]
) -> None:
    lead = await crm_api.client.post(f"{_CRM}/leads", json={"company_name": "Act Co"})
    lead_id = lead.json()["id"]
    await crm_api.client.post(
        f"{_CRM}/activities",
        json={"activity_type": "CALL", "subject": "C", "lead_id": lead_id},
    )
    await assert_query_budget(
        crm_api.client, query_counter, f"{_CRM}/activities?lead_id={lead_id}"
    )


# --- RBAC ---------------------------------------------------------------------


async def test_manage_cannot_convert(
    client: AsyncClient,
    crm_user_factory: Callable[..., object],
    db_session,
) -> None:
    """A principal with manage (but NOT convert) is 403 on the opportunity convert endpoint — the
    distinct convert key is enforced (D-009)."""
    from tests.modules.crm.factories import build_crm_setup

    principal = await crm_user_factory(
        slug="crm-nomanage",
        email="m@crm-nomanage.test",
        keys=(
            "crm.lead.read",
            "crm.lead.manage",
            "crm.opportunity.read",
            "crm.opportunity.manage",
            "crm.activity.read",
            "crm.activity.manage",
        ),
    )
    setup = await build_crm_setup(db_session, principal.tenant_id)
    token = (
        await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": principal.tenant_slug,
                "email": principal.email,
                "password": principal.password,
            },
        )
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    create = await client.post(
        f"{_CRM}/opportunities",
        json={
            "name": "D",
            "company_name": "P",
            "currency_code": "USD",
            "lines": [
                {
                    "item_id": str(setup.item_id),
                    "quantity": "1",
                    "estimated_unit_price": "10",
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    opp_id = create.json()["id"]
    convert = await client.post(f"{_CRM}/opportunities/{opp_id}/convert", json={})
    assert convert.status_code == 403
    assert convert.json()["error"]["code"] == "rbac.permission_denied"


async def test_read_only_cannot_create_lead(
    client: AsyncClient, crm_user_factory: Callable[..., object]
) -> None:
    principal = await crm_user_factory(
        slug="crm-ro",
        email="ro@crm-ro.test",
        keys=("crm.lead.read", "crm.opportunity.read", "crm.activity.read"),
    )
    token = (
        await client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": principal.tenant_slug,
                "email": principal.email,
                "password": principal.password,
            },
        )
    ).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"{_CRM}/leads", json={"company_name": "X"})
    assert resp.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(crm_api: CrmApi, crm_client_b: AsyncClient) -> None:
    """Tenant B cannot read tenant A's lead (the D-007 filter resolves it as a 404)."""
    create = await crm_api.client.post(f"{_CRM}/leads", json={"company_name": "A only"})
    lead_id = create.json()["id"]
    cross = await crm_client_b.get(f"{_CRM}/leads/{lead_id}")
    assert cross.status_code == 404
