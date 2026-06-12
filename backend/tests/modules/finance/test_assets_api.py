"""Asset accounting HTTP API (PLAN 4.10): lifecycle over HTTP, idempotent activation + run,
the 201/202 sync-background threshold, RBAC, tenant isolation, pagination + query budgets."""

import uuid
from datetime import date
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import JobStatus, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.finance import service
from app.modules.finance.assets_schemas import AssetCreate
from app.modules.finance.constants import (
    FINANCE_ASSET_MANAGE,
    FINANCE_ASSET_READ,
    DepreciationMethod,
)
from tests.conftest import assert_query_budget
from tests.modules.finance.factories_assets import AssetSetup, build_asset_setup


def _asset_body(setup: AssetSetup, **overrides) -> dict:
    body = {
        "name": "CNC Lathe",
        "acquisition_date": "2026-01-10",
        "acquisition_cost": "12000",
        "salvage_value": "0",
        "useful_life_months": 12,
        "depreciation_method": "STRAIGHT_LINE",
        "asset_account_id": str(setup.accounts["1500"]),
        "accumulated_depreciation_account_id": str(setup.accounts["1510"]),
        "depreciation_expense_account_id": str(setup.accounts["5100"]),
        "currency_code": "USD",
    }
    body.update(overrides)
    return body


async def _tenant_of(client: AsyncClient) -> uuid.UUID:
    me = await client.get("/api/v1/auth/me")
    return uuid.UUID(me.json()["tenant_id"])


async def _bootstrap(db_session: AsyncSession, client: AsyncClient) -> AssetSetup:
    return await build_asset_setup(db_session, await _tenant_of(client))


async def _first_period_id(client: AsyncClient) -> str:
    periods = await client.get("/api/v1/finance/fiscal-periods?limit=1")
    return periods.json()["items"][0]["id"]


async def test_asset_lifecycle_over_http(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """create (201 DRAFT, no number) -> patch -> idempotent activate (number + acquisition
    journal) -> 409 on a fresh re-activate; the replayed key returns the same body."""
    setup = await _bootstrap(db_session, finance_client)
    created = await finance_client.post("/api/v1/finance/assets", json=_asset_body(setup))
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"
    assert created.json()["asset_number"] is None
    asset_id = created.json()["id"]

    patched = await finance_client.patch(
        f"/api/v1/finance/assets/{asset_id}", json={"name": "CNC Lathe XL"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "CNC Lathe XL"

    activated = await finance_client.post(
        f"/api/v1/finance/assets/{asset_id}/activate",
        json={"capitalize": True},
        headers={"Idempotency-Key": "act-1"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["asset_number"] == "AST-2026-00001"
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["capitalized_journal_entry_id"] is not None

    replay = await finance_client.post(
        f"/api/v1/finance/assets/{asset_id}/activate",
        json={"capitalize": True},
        headers={"Idempotency-Key": "act-1"},
    )
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json() == activated.json()

    fresh_key = await finance_client.post(
        f"/api/v1/finance/assets/{asset_id}/activate",
        json={"capitalize": True},
        headers={"Idempotency-Key": "act-2"},
    )
    assert fresh_key.status_code == 409  # not DRAFT any more

    invalid = await finance_client.post(
        "/api/v1/finance/assets",
        json=_asset_body(setup, salvage_value="99999"),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "finance.asset_salvage_exceeds_cost"


async def test_depreciation_run_inline_201_and_idempotent(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """<= 100 eligible assets runs inline (201 run); a replayed key returns the same run; the
    run/entries/register read endpoints reflect it."""
    setup = await _bootstrap(db_session, finance_client)
    for index in range(2):
        created = await finance_client.post(
            "/api/v1/finance/assets", json=_asset_body(setup, name=f"Asset {index}")
        )
        activated = await finance_client.post(
            f"/api/v1/finance/assets/{created.json()['id']}/activate",
            json={"capitalize": False},
            headers={"Idempotency-Key": f"act-{index}"},
        )
        assert activated.status_code == 200, activated.text
    period_id = await _first_period_id(finance_client)

    run = await finance_client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": period_id, "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "run-1"},
    )
    assert run.status_code == 201, run.text
    assert run.json()["run_number"] == "DEP-2026-00001"
    assert run.json()["asset_count"] == 2
    assert Decimal(run.json()["total_amount"]) == Decimal("2000")
    run_id = run.json()["id"]

    replay = await finance_client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": period_id, "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "run-1"},
    )
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert replay.json()["id"] == run_id

    detail = await finance_client.get(f"/api/v1/finance/depreciation-runs/{run_id}")
    assert detail.status_code == 200
    entries = await finance_client.get(
        f"/api/v1/finance/depreciation-runs/{run_id}/entries"
    )
    assert len(entries.json()["items"]) == 2
    register = await finance_client.get("/api/v1/finance/asset-register?as_of=2026-01-31")
    assert register.status_code == 200, register.text
    assert len(register.json()["items"]) == 2
    first_row = register.json()["items"][0]
    assert Decimal(first_row["accumulated_depreciation"]) == Decimal("1000")
    assert Decimal(first_row["net_book_value"]) == Decimal("11000")


async def test_large_run_returns_202_and_completes_in_background(
    finance_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PERFORMANCE §3: 120 eligible assets > the 100 sync max -> 202 {job_id}; the job
    completes the SAME run logic; a replayed key returns the SAME job id (D-013)."""
    setup = await _bootstrap(db_session, finance_client)
    with tenant_context(setup.tenant_id):
        for index in range(120):
            asset = await service.create_asset(
                db_session,
                setup.tenant_id,
                AssetCreate(
                    name=f"Bulk {index:03d}",
                    acquisition_date=date(2026, 1, 5),
                    acquisition_cost=Decimal("1200"),
                    useful_life_months=12,
                    depreciation_method=DepreciationMethod.STRAIGHT_LINE,
                    asset_account_id=setup.accounts["1500"],
                    accumulated_depreciation_account_id=setup.accounts["1510"],
                    depreciation_expense_account_id=setup.accounts["5100"],
                    currency_code="USD",
                ),
            )
            await service.activate_asset(
                db_session, setup.tenant_id, asset.id, capitalize=False
            )
        await db_session.commit()
    period_id = await _first_period_id(finance_client)

    accepted = await finance_client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": period_id, "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "big-run"},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["status"] == JobStatus.PENDING.value
    job_id = accepted.json()["job_id"]

    replay = await finance_client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": period_id, "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "big-run"},
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == job_id

    await wait_for_jobs()
    job = await finance_client.get(f"/api/v1/jobs/{job_id}")
    assert job.json()["status"] == JobStatus.COMPLETED.value, job.text
    assert job.json()["result"]["asset_count"] == 120
    run_id = job.json()["result"]["run_id"]

    run = await finance_client.get(f"/api/v1/finance/depreciation-runs/{run_id}")
    assert run.json()["asset_count"] == 120
    assert Decimal(run.json()["total_amount"]) == Decimal("12000")  # 120 x 100
    entries = await finance_client.get(
        f"/api/v1/finance/depreciation-runs/{run_id}/entries?limit=200"
    )
    assert len(entries.json()["items"]) == 120


async def test_lists_paginate_within_query_budget(
    finance_client: AsyncClient, db_session: AsyncSession, query_counter
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    for index in range(3):
        resp = await finance_client.post(
            "/api/v1/finance/assets",
            json=_asset_body(
                setup, name=f"Asset {index}", acquisition_date=f"2026-01-0{index + 1}"
            ),
        )
        assert resp.status_code == 201, resp.text
        await finance_client.post(
            f"/api/v1/finance/assets/{resp.json()['id']}/activate",
            json={"capitalize": False},
            headers={"Idempotency-Key": f"page-act-{index}"},
        )
    period_id = await _first_period_id(finance_client)
    run = await finance_client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": period_id, "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "page-run"},
    )
    run_id = run.json()["id"]

    first_page = await finance_client.get("/api/v1/finance/assets?limit=2")
    assert len(first_page.json()["items"]) == 2
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None
    second_page = await finance_client.get(f"/api/v1/finance/assets?limit=2&cursor={cursor}")
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["next_cursor"] is None

    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/assets?limit=2")
    await assert_query_budget(finance_client, query_counter, "/api/v1/finance/depreciation-runs")
    await assert_query_budget(
        finance_client,
        query_counter,
        f"/api/v1/finance/depreciation-runs/{run_id}/entries",
    )
    await assert_query_budget(
        finance_client, query_counter, "/api/v1/finance/asset-register?as_of=2026-01-31"
    )


async def _narrow_client(
    client: AsyncClient, finance_user_factory, slug: str, email: str, keys: tuple[str, ...]
):
    principal = await finance_user_factory(slug=slug, email=email, keys=keys)
    login = await client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": slug, "email": email, "password": principal.password},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return principal


async def test_asset_writes_require_manage_permission(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    principal = await _narrow_client(
        client, finance_user_factory, "asset-reader", "r@asset.test", (FINANCE_ASSET_READ,)
    )
    setup = await build_asset_setup(db_session, principal.tenant_id)
    create = await client.post("/api/v1/finance/assets", json=_asset_body(setup))
    assert create.status_code == 403
    activate = await client.post(
        f"/api/v1/finance/assets/{uuid.uuid4()}/activate",
        json={"capitalize": False},
        headers={"Idempotency-Key": "rbac-act"},
    )
    assert activate.status_code == 403
    assert (await client.get("/api/v1/finance/assets")).status_code == 200


async def test_depreciation_run_requires_its_own_permission(
    client: AsyncClient, db_session: AsyncSession, finance_user_factory
) -> None:
    """asset.manage alone cannot run depreciation — posting a journal is its own action."""
    principal = await _narrow_client(
        client,
        finance_user_factory,
        "asset-manager",
        "m@asset.test",
        (FINANCE_ASSET_READ, FINANCE_ASSET_MANAGE),
    )
    await build_asset_setup(db_session, principal.tenant_id)
    run = await client.post(
        "/api/v1/finance/depreciation-runs",
        json={"fiscal_period_id": str(uuid.uuid4()), "run_date": "2026-01-31"},
        headers={"Idempotency-Key": "rbac-run"},
    )
    assert run.status_code == 403


async def test_assets_are_tenant_isolated_over_http(
    client: AsyncClient, finance_client: AsyncClient, db_session: AsyncSession,
    finance_user_factory,
) -> None:
    setup = await _bootstrap(db_session, finance_client)
    created = await finance_client.post("/api/v1/finance/assets", json=_asset_body(setup))
    asset_id = created.json()["id"]

    await _narrow_client(
        client,
        finance_user_factory,
        "asset-other",
        "o@asset.test",
        (FINANCE_ASSET_READ, FINANCE_ASSET_MANAGE),
    )
    foreign = await client.get(f"/api/v1/finance/assets/{asset_id}")
    assert foreign.status_code == 404
    assert (await client.get("/api/v1/finance/assets")).json()["items"] == []
    assert (await client.get("/api/v1/finance/asset-register?as_of=2026-12-31")).json()[
        "items"
    ] == []
