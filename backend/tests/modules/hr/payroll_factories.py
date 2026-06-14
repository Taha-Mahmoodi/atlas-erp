"""HR payroll test data builders (PLAN 10.4, D-055), behind tests/modules/hr/conftest.py.

A payroll run posts a consolidated finance journal via the event bus, so the setup wires the FINANCE
side a run needs: a functional currency (the run/journal currency), an open 2026 fiscal year, the
three payroll posting defaults (salary-expense / wages-payable / payroll-tax-payable), plus the HR
side (a cost centre + department + a few salaried employees). Builders go through the REAL service
layer under the tenant context (D-025). Kept a SEPARATE factory file from factories.py (the cap).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import tenant_context
from app.modules.finance import service as finance_service
from app.modules.finance.constants import (
    PAYROLL_TAX_PAYABLE,
    SALARY_EXPENSE,
    WAGES_PAYABLE,
    AccountType,
)
from app.modules.finance.schemas import AccountCreate, FiscalYearCreate
from app.modules.hr.models import Employee
from tests.modules.hr.factories import build_cost_center, build_department, build_employee

# (purpose, code, name, account_type) for the three payroll posting defaults.
_PAYROLL_ACCOUNTS: tuple[tuple[str, str, str, AccountType], ...] = (
    (SALARY_EXPENSE, "6100", "Salary expense", AccountType.EXPENSE),
    (WAGES_PAYABLE, "2300", "Wages payable", AccountType.LIABILITY),
    (PAYROLL_TAX_PAYABLE, "2310", "Payroll tax payable", AccountType.LIABILITY),
)


@dataclass(frozen=True)
class PayrollSetup:
    """A tenant wired for the full payroll flow (PLAN 10.4): the three posting-default account ids
    by purpose, the cost-centre id (carried on the department), the department id, and the salaried
    employee ids in employee_code order. Plain ids so a rollback (expiring loaded ORM objects)
    cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    accounts: dict[str, uuid.UUID]
    cost_center_id: uuid.UUID
    department_id: uuid.UUID
    employee_ids: tuple[uuid.UUID, ...]
    salaries: tuple[Decimal, ...]


async def build_payroll_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    map_defaults: bool = True,
    salaries: tuple[Decimal, ...] = (Decimal("5000"), Decimal("3000")),
    with_cost_center: bool = True,
) -> PayrollSetup:
    """Wire a tenant for the payroll-run flow (PLAN 10.4). Creates a functional USD currency + an
    open 2026 fiscal year, maps the three payroll posting defaults (unless ``map_defaults`` is
    False — the unmapped-error tests), and a department (carrying a cost centre when
    ``with_cost_center``) with one salaried employee per entry in ``salaries``."""
    accounts: dict[str, uuid.UUID] = {}
    with tenant_context(tenant_id):
        await finance_service.create_currency(
            session, tenant_id, code="USD", name="US Dollar", is_functional=True
        )
        await finance_service.create_fiscal_year(
            session,
            tenant_id,
            FiscalYearCreate(code="2026", name="FY2026", start_date=date(2026, 1, 1)),
        )
        await session.commit()
        for purpose, code, name, atype in _PAYROLL_ACCOUNTS:
            account = await finance_service.create_account(
                session, tenant_id, AccountCreate(code=code, name=name, account_type=atype)
            )
            accounts[purpose] = account.id
            await session.commit()
            if map_defaults:
                await finance_service.set_posting_default(session, tenant_id, purpose, account.id)
                await session.commit()

    cost_center_id: uuid.UUID | None = None
    if with_cost_center:
        cost_center_id = await build_cost_center(session, tenant_id)
    department = await build_department(
        session, tenant_id, cost_center_id=cost_center_id
    )

    employee_ids: list[uuid.UUID] = []
    for index, salary in enumerate(salaries):
        employee = await build_employee(
            session,
            tenant_id,
            employee_code=f"EMP-{200 + index}",
            first_name=f"Worker{index}",
            department_id=department.id,
            base_salary=salary,
            currency_code="USD",
        )
        employee_ids.append(employee.id)

    return PayrollSetup(
        tenant_id=tenant_id,
        accounts=accounts,
        cost_center_id=cost_center_id or uuid.uuid4(),
        department_id=department.id,
        employee_ids=tuple(employee_ids),
        salaries=salaries,
    )


async def build_unsalaried_employee(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: uuid.UUID,
    *,
    employee_code: str = "EMP-NOSAL",
) -> Employee:
    """An ACTIVE employee with NO base_salary (skipped by a payroll run, D-055)."""
    return await build_employee(
        session,
        tenant_id,
        employee_code=employee_code,
        first_name="NoSalary",
        department_id=department_id,
        base_salary=None,
        currency_code=None,
    )
