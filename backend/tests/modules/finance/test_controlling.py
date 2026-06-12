"""Controlling master data + journal-dimension validation (PLAN 4.7), SQLite.

Proves cost/profit-centre CRUD + the acyclic-hierarchy + unique-code rules, allocation-rule target
validation against the basis (PERCENT sums to 100, FIXED_WEIGHT any positive), the journal's
service-level dimension integrity (a line with an unknown cost/profit centre is rejected; a valid
one posts and the line carries it, the D-022 replacement for the absent FK), the cost_center_balance
query, RBAC, and tenant isolation. The allocation RUN engine is proven in test_allocation.py.
"""

from collections.abc import AsyncIterator, Callable
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries, service
from app.modules.finance.constants import FINANCE_COST_CENTER_READ, AllocationBasis
from app.modules.finance.controlling_schemas import (
    AllocationRuleCreate,
    AllocationTargetCreate,
    CostCenterCreate,
    CostCenterUpdate,
    ProfitCenterCreate,
)
from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.finance.conftest import CoSetup, FinancePrincipal, JournalSetup

_PD = date(2026, 3, 15)


# --- Cost / profit centre CRUD ------------------------------------------------


async def test_create_cost_center(db_session: AsyncSession, co_setup: CoSetup) -> None:
    with tenant_context(co_setup.tenant_id):
        center = await service.create_cost_center(
            db_session, co_setup.tenant_id, CostCenterCreate(code="CC100", name="Production")
        )
        await db_session.commit()
    assert center.code == "CC100"
    assert center.is_active is True


async def test_duplicate_cost_center_code_rejected(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        await service.create_cost_center(
            db_session, co_setup.tenant_id, CostCenterCreate(code="CC1", name="A")
        )
        await db_session.commit()
        with pytest.raises(ConflictError) as exc:
            await service.create_cost_center(
                db_session, co_setup.tenant_id, CostCenterCreate(code="CC1", name="B")
            )
    assert exc.value.code == "finance.cost_center_code_conflict"


async def test_cost_center_hierarchy_and_cycle_rejected(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        parent = await service.create_cost_center(
            db_session, co_setup.tenant_id, CostCenterCreate(code="P", name="Parent")
        )
        child = await service.create_cost_center(
            db_session,
            co_setup.tenant_id,
            CostCenterCreate(code="C", name="Child", parent_id=parent.id),
        )
        await db_session.commit()
        assert child.parent_id == parent.id
        # Reparenting the parent under its own child would form a cycle.
        with pytest.raises(ValidationFailedError) as exc:
            await service.update_cost_center(
                db_session,
                co_setup.tenant_id,
                parent.id,
                CostCenterUpdate(parent_id=child.id),
            )
    assert exc.value.code == "finance.cost_center_cycle"


async def test_cost_center_cannot_be_its_own_parent(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        center = await service.create_cost_center(
            db_session, co_setup.tenant_id, CostCenterCreate(code="X", name="X")
        )
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as exc:
            await service.update_cost_center(
                db_session,
                co_setup.tenant_id,
                center.id,
                CostCenterUpdate(parent_id=center.id),
            )
    assert exc.value.code == "finance.cost_center_cycle"


async def test_profit_center_crud_and_cost_center_default(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        pc = await service.create_profit_center(
            db_session, co_setup.tenant_id, ProfitCenterCreate(code="PC1", name="North")
        )
        cc = await service.create_cost_center(
            db_session,
            co_setup.tenant_id,
            CostCenterCreate(code="CC1", name="Sales", default_profit_center_id=pc.id),
        )
        await db_session.commit()
    assert cc.default_profit_center_id == pc.id


async def test_cost_center_unknown_default_profit_center_rejected(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    import uuid

    with tenant_context(co_setup.tenant_id), pytest.raises(NotFoundError):
        await service.create_cost_center(
            db_session,
            co_setup.tenant_id,
            CostCenterCreate(code="CC1", name="X", default_profit_center_id=uuid.uuid4()),
        )


# --- Allocation-rule target validation ----------------------------------------


async def _two_centers(
    db_session: AsyncSession, co_setup: CoSetup
) -> tuple[object, list[object]]:
    """A source cost centre + three target cost centres."""
    source = await service.create_cost_center(
        db_session, co_setup.tenant_id, CostCenterCreate(code="SRC", name="Source")
    )
    targets = []
    for code in ("T1", "T2", "T3"):
        targets.append(
            await service.create_cost_center(
                db_session, co_setup.tenant_id, CostCenterCreate(code=code, name=code)
            )
        )
    return source, targets


async def test_percent_rule_must_sum_to_100(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        source, targets = await _two_centers(db_session, co_setup)
        await db_session.commit()
        bad = AllocationRuleCreate(
            code="R1",
            name="Bad",
            source_cost_center_id=source.id,
            basis=AllocationBasis.PERCENT,
            targets=[
                AllocationTargetCreate(target_cost_center_id=targets[0].id, weight=Decimal(50)),
                AllocationTargetCreate(target_cost_center_id=targets[1].id, weight=Decimal(30)),
            ],
        )
        with pytest.raises(ValidationFailedError) as exc:
            await service.create_allocation_rule(db_session, co_setup.tenant_id, bad)
    assert exc.value.code == "finance.allocation_percent_not_100"


async def test_percent_rule_summing_to_100_accepted(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        source, targets = await _two_centers(db_session, co_setup)
        await db_session.commit()
        rule = await service.create_allocation_rule(
            db_session,
            co_setup.tenant_id,
            AllocationRuleCreate(
                code="R1",
                name="Good",
                source_cost_center_id=source.id,
                basis=AllocationBasis.PERCENT,
                targets=[
                    AllocationTargetCreate(target_cost_center_id=targets[0].id, weight=Decimal(50)),
                    AllocationTargetCreate(target_cost_center_id=targets[1].id, weight=Decimal(30)),
                    AllocationTargetCreate(target_cost_center_id=targets[2].id, weight=Decimal(20)),
                ],
            ),
        )
        await db_session.commit()
        rule_targets = await service.get_rule_targets(db_session, co_setup.tenant_id, rule.id)
    assert len(rule_targets) == 3


async def test_fixed_weight_rule_any_positive_accepted(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        source, targets = await _two_centers(db_session, co_setup)
        await db_session.commit()
        rule = await service.create_allocation_rule(
            db_session,
            co_setup.tenant_id,
            AllocationRuleCreate(
                code="R1",
                name="Headcount",
                source_cost_center_id=source.id,
                basis=AllocationBasis.FIXED_WEIGHT,
                targets=[
                    AllocationTargetCreate(target_cost_center_id=targets[0].id, weight=Decimal(3)),
                    AllocationTargetCreate(target_cost_center_id=targets[1].id, weight=Decimal(1)),
                ],
            ),
        )
        await db_session.commit()
    assert rule.basis == AllocationBasis.FIXED_WEIGHT.value


async def test_source_cannot_be_a_target(
    db_session: AsyncSession, co_setup: CoSetup
) -> None:
    with tenant_context(co_setup.tenant_id):
        source, _targets = await _two_centers(db_session, co_setup)
        await db_session.commit()
        with pytest.raises(ValidationFailedError) as exc:
            await service.create_allocation_rule(
                db_session,
                co_setup.tenant_id,
                AllocationRuleCreate(
                    code="R1",
                    name="Self",
                    source_cost_center_id=source.id,
                    basis=AllocationBasis.FIXED_WEIGHT,
                    targets=[
                        AllocationTargetCreate(
                            target_cost_center_id=source.id, weight=Decimal(1)
                        )
                    ],
                ),
            )
    assert exc.value.code == "finance.allocation_target_is_source"


# --- Journal dimension validation (D-022 service-level integrity) -------------


def _balanced_with_cost_center(
    setup: JournalSetup, cost_center_id, amount: str = "100.00"
) -> JournalEntryCreate:
    return JournalEntryCreate(
        posting_date=_PD,
        currency_code="USD",
        description="dim test",
        lines=[
            JournalLineCreate(
                account_id=setup.accounts["5000"],
                transaction_debit_amount=Decimal(amount),
                cost_center_id=cost_center_id,
            ),
            JournalLineCreate(
                account_id=setup.accounts["1000"],
                transaction_credit_amount=Decimal(amount),
            ),
        ],
    )


async def test_journal_unknown_cost_center_rejected(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    import uuid

    payload = _balanced_with_cost_center(journal_setup, uuid.uuid4())
    with tenant_context(journal_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_draft_entry(db_session, journal_setup.tenant_id, payload)
    assert exc.value.code == "finance.journal_cost_center_not_found"


async def test_journal_valid_cost_center_posts_and_line_carries_it(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    with tenant_context(journal_setup.tenant_id):
        cc = await service.create_cost_center(
            db_session, journal_setup.tenant_id, CostCenterCreate(code="CC1", name="Ops")
        )
        await db_session.commit()
        entry = await service.create_draft_entry(
            db_session,
            journal_setup.tenant_id,
            _balanced_with_cost_center(journal_setup, cc.id),
        )
        await service.post_entry(db_session, journal_setup.tenant_id, entry.id)
        await db_session.commit()
        _, lines = await service.get_entry_with_lines(
            db_session, journal_setup.tenant_id, entry.id
        )
    debit_line = next(line for line in lines if line.transaction_debit_amount > 0)
    assert debit_line.cost_center_id == cc.id
    assert debit_line.is_posted is True


async def test_cost_center_balance_query(
    db_session: AsyncSession, journal_setup: JournalSetup
) -> None:
    """The balance query returns the cost centre's net posted balance for the period (D-021)."""
    with tenant_context(journal_setup.tenant_id):
        cc = await service.create_cost_center(
            db_session, journal_setup.tenant_id, CostCenterCreate(code="CC1", name="Ops")
        )
        await db_session.commit()
        # Pre-posting: zero balance.
        period = await queries.find_period_for_date(db_session, journal_setup.tenant_id, _PD)
        assert (
            await queries.cost_center_balance(
                db_session, journal_setup.tenant_id, cc.id, period.id
            )
            == Decimal(0)
        )
        entry = await service.create_draft_entry(
            db_session,
            journal_setup.tenant_id,
            _balanced_with_cost_center(journal_setup, cc.id, "250.00"),
        )
        await service.post_entry(db_session, journal_setup.tenant_id, entry.id)
        await db_session.commit()
        balance = await queries.cost_center_balance(
            db_session, journal_setup.tenant_id, cc.id, period.id
        )
    # The 5000 expense line debited 250 with this cost centre → net debit 250.
    assert balance == Decimal("250.00")


# --- Tenant isolation + RBAC --------------------------------------------------


async def test_cost_center_tenant_isolation(
    db_session: AsyncSession, tenant_a, tenant_b
) -> None:
    with tenant_context(tenant_a):
        center = await service.create_cost_center(
            db_session, tenant_a, CostCenterCreate(code="CC1", name="A")
        )
        await db_session.commit()
    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_cost_center(db_session, tenant_b, center.id)


async def test_cost_center_read_cannot_create(
    client: AsyncClient,
    finance_user_factory: Callable[..., "AsyncIterator[FinancePrincipal]"],
) -> None:
    principal = await finance_user_factory(
        slug="ccro-acme", email="ccro@acme.test", keys=(FINANCE_COST_CENTER_READ,)
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
    forbidden = await client.post(
        "/api/v1/finance/cost-centers", json={"code": "CC1", "name": "Ops"}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "rbac.permission_denied"


async def test_cost_center_crud_via_api(finance_client: AsyncClient) -> None:
    created = await finance_client.post(
        "/api/v1/finance/cost-centers", json={"code": "CC1", "name": "Ops"}
    )
    assert created.status_code == 201, created.text
    cc_id = created.json()["id"]
    listed = await finance_client.get("/api/v1/finance/cost-centers")
    assert listed.status_code == 200
    assert any(item["id"] == cc_id for item in listed.json()["items"])
    patched = await finance_client.patch(
        f"/api/v1/finance/cost-centers/{cc_id}", json={"is_active": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False


async def test_co_list_endpoints_query_count(
    finance_client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    """PERFORMANCE §2: warm-path cost-centre/profit-centre/allocation-rule lists ≤3 queries."""
    cc_ids: list[str] = []
    for i in range(3):
        cc = await finance_client.post(
            "/api/v1/finance/cost-centers", json={"code": f"CC{i}", "name": f"Centre {i}"}
        )
        assert cc.status_code == 201, cc.text
        cc_ids.append(cc.json()["id"])
        pc = await finance_client.post(
            "/api/v1/finance/profit-centers", json={"code": f"PC{i}", "name": f"Profit {i}"}
        )
        assert pc.status_code == 201, pc.text
    rule = await finance_client.post(
        "/api/v1/finance/allocation-rules",
        json={
            "code": "SPREAD",
            "name": "Spread overhead",
            "source_cost_center_id": cc_ids[0],
            "targets": [
                {"target_cost_center_id": cc_ids[1], "weight": "60"},
                {"target_cost_center_id": cc_ids[2], "weight": "40"},
            ],
        },
    )
    assert rule.status_code == 201, rule.text
    for url in (
        "/api/v1/finance/cost-centers",
        "/api/v1/finance/profit-centers",
        "/api/v1/finance/allocation-rules",
    ):
        await assert_query_budget(finance_client, query_counter, url)
