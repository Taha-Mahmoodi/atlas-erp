"""The tax engine (PLAN 4.4), SQLite.

Proves: exclusive tax (net 100 @ 20% -> tax 20, gross 120); inclusive tax (gross 120 @ 20% ->
net 100, tax 20) including an awkward rate (19.6%, ROUND_HALF_UP); zero-rate and a reduced rate;
half-cent rounding rounds HALF_UP and document-level grouping sums exactly per code (allocate);
direction picks the payable (OUTPUT) vs receivable (INPUT) account; CRUD + unique code + RBAC on
finance.tax.manage + tenant isolation; and the queries interface returns the right code/calculation.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.finance import queries, service
from app.modules.finance.constants import (
    FINANCE_TAX_READ,
    AccountType,
    TaxDirection,
)
from app.modules.finance.models import TaxCode
from app.modules.finance.schemas import AccountCreate, TaxCodeCreate, TaxCodeUpdate
from tests.modules.finance.conftest import FinancePrincipal


async def _make_account(
    session: AsyncSession, tenant_id: uuid.UUID, code: str, name: str, atype: AccountType
) -> uuid.UUID:
    account = await service.create_account(
        session, tenant_id, AccountCreate(code=code, name=name, account_type=atype)
    )
    return account.id


async def _wired_tax_code(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "VAT20",
    rate: str = "20",
    is_inclusive: bool = False,
) -> TaxCode:
    """A tax code wired with both a payable (LIABILITY) and receivable (ASSET) account."""
    payable = await _make_account(session, tenant_id, "2100", "Output VAT", AccountType.LIABILITY)
    receivable = await _make_account(session, tenant_id, "1300", "Input VAT", AccountType.ASSET)
    tax_code = await service.create_tax_code(
        session,
        tenant_id,
        TaxCodeCreate(
            code=code,
            name=f"{code} tax",
            rate_percent=Decimal(rate),
            jurisdiction="GB",
            is_inclusive=is_inclusive,
            tax_payable_account_id=payable,
            tax_receivable_account_id=receivable,
        ),
    )
    await session.commit()
    return tax_code


# --- exclusive / inclusive math -----------------------------------------------


async def test_exclusive_tax_adds_on_top(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
        calc = service.calculate_line_tax(
            Decimal("100.00"), tax_code, direction=TaxDirection.OUTPUT
        )
    assert calc.net_amount == Decimal("100.00")
    assert calc.tax_amount == Decimal("20.00")
    assert calc.gross_amount == Decimal("120.00")


async def test_inclusive_tax_extracted_from_gross(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a, is_inclusive=True)
        calc = service.calculate_line_tax(
            Decimal("120.00"), tax_code, direction=TaxDirection.OUTPUT
        )
    # Gross 120 @ 20% inclusive -> net 100, tax 20, and net + tax == gross exactly.
    assert calc.net_amount == Decimal("100.00")
    assert calc.tax_amount == Decimal("20.00")
    assert calc.gross_amount == Decimal("120.00")
    assert calc.net_amount + calc.tax_amount == calc.gross_amount


async def test_inclusive_awkward_rate_rounds_half_up(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # 19.6% inclusive on 119.60: net = 119.60 / 1.196 = 100.00 exactly; tax = 19.60.
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(
            db_session, tenant_a, code="VAT196", rate="19.6", is_inclusive=True
        )
        calc = service.calculate_line_tax(
            Decimal("119.60"), tax_code, direction=TaxDirection.OUTPUT
        )
    assert calc.net_amount == Decimal("100.00")
    assert calc.tax_amount == Decimal("19.60")
    assert calc.net_amount + calc.tax_amount == calc.gross_amount


async def test_zero_rate_tax(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a, code="ZERO", rate="0")
        calc = service.calculate_line_tax(
            Decimal("100.00"), tax_code, direction=TaxDirection.OUTPUT
        )
    assert calc.tax_amount == Decimal("0.00")
    assert calc.net_amount == calc.gross_amount == Decimal("100.00")


async def test_reduced_rate_tax(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    # A reduced 5% rate, exclusive: 200.00 net -> 10.00 tax, 210.00 gross.
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a, code="VAT5", rate="5")
        calc = service.calculate_line_tax(
            Decimal("200.00"), tax_code, direction=TaxDirection.OUTPUT
        )
    assert calc.tax_amount == Decimal("10.00")
    assert calc.gross_amount == Decimal("210.00")


# --- rounding -----------------------------------------------------------------


async def test_line_half_cent_rounds_half_up(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    # 7.5% of 10.00 = 0.75 exactly; pick a base producing a half-cent: 12.34 @ 20% = 2.468 -> 2.47.
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
        calc = service.calculate_line_tax(
            Decimal("12.34"), tax_code, direction=TaxDirection.OUTPUT
        )
    # 12.34 * 0.20 = 2.468 -> HALF_UP -> 2.47.
    assert calc.tax_amount == Decimal("2.47")
    assert calc.gross_amount == Decimal("14.81")


async def test_document_tax_groups_per_code_and_sums_exactly(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
        # Three lines under the same code: nets 33.33 + 33.33 + 33.34 = 100.00.
        summary = service.calculate_document_tax(
            [
                (Decimal("33.33"), tax_code, TaxDirection.OUTPUT),
                (Decimal("33.33"), tax_code, TaxDirection.OUTPUT),
                (Decimal("33.34"), tax_code, TaxDirection.OUTPUT),
            ]
        )
    # One tax line per code; tax on the GROUP net 100.00 @ 20% = 20.00 exactly (not the drifting
    # sum of per-line rounded tax 6.67 + 6.67 + 6.67 = 20.01).
    assert len(summary.tax_lines) == 1
    assert summary.net_total == Decimal("100.00")
    assert summary.tax_total == Decimal("20.00")
    assert summary.gross_total == Decimal("120.00")
    tax_line = summary.tax_lines[0]
    assert tax_line.tax_amount == Decimal("20.00")
    # The per-line tax split reconstitutes the group tax EXACTLY (allocate, no drift).
    assert len(tax_line.line_tax) == 3
    assert sum(tax_line.line_tax, Decimal(0)) == Decimal("20.00")


async def test_document_tax_groups_distinct_codes_separately(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        vat20 = await _wired_tax_code(db_session, tenant_a)
        vat5 = await service.create_tax_code(
            db_session,
            tenant_a,
            TaxCodeCreate(code="VAT5", name="Reduced", rate_percent=Decimal("5")),
        )
        await db_session.commit()
        summary = service.calculate_document_tax(
            [
                (Decimal("100.00"), vat20, TaxDirection.OUTPUT),
                (Decimal("100.00"), vat5, TaxDirection.OUTPUT),
            ]
        )
    assert len(summary.tax_lines) == 2
    by_code = {line.tax_code: line.tax_amount for line in summary.tax_lines}
    assert by_code["VAT20"] == Decimal("20.00")
    assert by_code["VAT5"] == Decimal("5.00")
    assert summary.tax_total == Decimal("25.00")


# --- direction picks the account ----------------------------------------------


async def test_direction_picks_payable_for_output(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
        out = service.calculate_line_tax(
            Decimal("100.00"), tax_code, direction=TaxDirection.OUTPUT
        )
        inp = service.calculate_line_tax(
            Decimal("100.00"), tax_code, direction=TaxDirection.INPUT
        )
    assert out.tax_account_id == tax_code.tax_payable_account_id
    assert inp.tax_account_id == tax_code.tax_receivable_account_id
    assert out.tax_account_id != inp.tax_account_id


# --- CRUD + uniqueness + validation -------------------------------------------


async def test_create_get_update_tax_code(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
        fetched = await service.get_tax_code(db_session, tenant_a, tax_code.id)
        assert fetched.code == "VAT20"
        updated = await service.update_tax_code(
            db_session, tenant_a, tax_code.id, TaxCodeUpdate(rate_percent=Decimal("17.5"))
        )
        await db_session.commit()
    assert Decimal(str(updated.rate_percent)) == Decimal("17.5")


async def test_duplicate_code_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await _wired_tax_code(db_session, tenant_a)
        with pytest.raises(ConflictError) as exc:
            await service.create_tax_code(
                db_session,
                tenant_a,
                TaxCodeCreate(code="VAT20", name="Dup", rate_percent=Decimal("20")),
            )
    assert exc.value.code == "finance.tax_code_conflict"


async def test_create_rejects_unknown_account(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_tax_code(
            db_session,
            tenant_a,
            TaxCodeCreate(
                code="BAD",
                name="Bad wiring",
                rate_percent=Decimal("20"),
                tax_payable_account_id=uuid.uuid4(),
            ),
        )
    assert exc.value.code == "finance.tax_account_not_found"


async def test_get_unknown_tax_code_raises(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError) as exc:
        await service.get_tax_code(db_session, tenant_a, uuid.uuid4())
    assert exc.value.code == "finance.tax_code_not_found"


# --- tenant isolation ---------------------------------------------------------


async def test_tax_code_tenant_isolation(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        tax_code = await _wired_tax_code(db_session, tenant_a)
    # Tenant B cannot read tenant A's tax code (the D-007 filter + explicit tenant guard).
    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await service.get_tax_code(db_session, tenant_b, tax_code.id)
    # And the by-code query is tenant-scoped: B sees None.
    with tenant_context(tenant_b):
        assert await queries.get_tax_code(db_session, tenant_b, "VAT20") is None


# --- queries interface --------------------------------------------------------


async def test_queries_get_tax_code_and_calculate(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await _wired_tax_code(db_session, tenant_a)
        resolved = await queries.get_tax_code(db_session, tenant_a, "VAT20")
        assert resolved is not None
        assert resolved.code == "VAT20"
        calc = queries.calculate_line_tax(
            Decimal("100.00"), resolved, direction=TaxDirection.OUTPUT
        )
    assert calc.tax_amount == Decimal("20.00")
    assert calc.tax_account_id == resolved.tax_payable_account_id


# --- RBAC + API ---------------------------------------------------------------


async def test_tax_manage_required_to_create_code(
    client: AsyncClient,
    finance_user_factory: Callable[..., "AsyncIterator[FinancePrincipal]"],
) -> None:
    principal = await finance_user_factory(
        slug="taxro-acme", email="taxro@acme.test", keys=(FINANCE_TAX_READ,)
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
        "/api/v1/finance/tax-codes",
        json={"code": "VAT20", "name": "VAT", "rate_percent": "20"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "rbac.permission_denied"


async def test_tax_code_crud_via_api(finance_client: AsyncClient) -> None:
    created = await finance_client.post(
        "/api/v1/finance/tax-codes",
        json={
            "code": "VAT20",
            "name": "Standard VAT",
            "rate_percent": "20",
            "jurisdiction": "GB",
            "is_inclusive": False,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"] == "VAT20"
    assert body["rate_percent"] == "20.000000"

    listed = await finance_client.get("/api/v1/finance/tax-codes")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    patched = await finance_client.patch(
        f"/api/v1/finance/tax-codes/{body['id']}", json={"is_active": False}
    )
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False
