"""Leave accrual run (PLAN 10.2, D-053): grant each ACTIVE employee the per-period
``accrual_amount`` of each ACTIVE leave type of a frequency, capped at ``max_balance``, idempotent
per period.

THE RUN (the maintenance preventive-generation analogue, set-based — PERFORMANCE §2). For a
frequency (MONTHLY|ANNUAL) and an ``as_of`` date the run derives the PERIOD KEY (YYYY-MM for
MONTHLY, YYYY for ANNUAL), then for every (active employee × active leave type of that frequency) it
grants ``accrual_amount`` to the pair's balance unless it was already accrued for that period.

THE IDEMPOTENCY GUARD (D-053). Each balance carries ``last_accrual_period``. The run grants a pair
only when its balance's ``last_accrual_period`` != the run period, then stamps it with the period.
So a same-period re-run finds every balance already stamped and grants nothing — the
generate-once-per-period guarantee, the maintenance next-due-date idempotency analogue.

THE CAP (D-053). When ``max_balance`` is set, the grant is clamped so ``balance_days`` never exceeds
the cap: a balance already at/over the cap gains nothing this period (but is still stamped, so it is
not re-granted later); a partial grant lifts it exactly to the cap. ``accrued_to_date`` records only
what was actually granted.

SET-BASED reads (two queries: the active employees, the active leave types of the frequency; plus
the existing balances for the pairs) feed an in-memory cross-product — no per-pair N+1 in the scan
(PERFORMANCE §2). New balances are inserted; existing ones mutated.

``from __future__ import annotations`` keeps the model annotations strings at import.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.constants import AccrualFrequency, EmploymentStatus
from app.modules.hr.models import Employee, LeaveBalance, LeaveType


def accrual_period_key(frequency: AccrualFrequency, as_of: date) -> str:
    """The period key the run keys idempotency off (D-053): ``YYYY-MM`` for MONTHLY, ``YYYY`` for
    ANNUAL. The ``hr_leave_balances.last_accrual_period`` column stores this string."""
    if AccrualFrequency(frequency) == AccrualFrequency.MONTHLY:
        return f"{as_of.year:04d}-{as_of.month:02d}"
    return f"{as_of.year:04d}"


def _capped_grant(current: Decimal, amount: Decimal, cap: Decimal | None) -> Decimal:
    """How much of ``amount`` to actually grant given the current balance and an optional cap
    (D-053): the full ``amount`` when uncapped, else clamped so ``current`` never exceeds ``cap`` —
    0 when already at/over the cap, the remaining headroom when a full grant would overshoot."""
    if cap is None:
        return amount
    headroom = cap - current
    if headroom <= 0:
        return Decimal(0)
    return min(amount, headroom)


async def accrue_leave(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    as_of: date,
    frequency: AccrualFrequency,
) -> tuple[str, int]:
    """Run accrual for ``frequency`` as of ``as_of`` (D-053). Grants ``accrual_amount`` to every
    (ACTIVE employee × ACTIVE leave type of ``frequency``) balance not yet accrued for the run's
    period, capped at ``max_balance``, then stamps each granted balance with the period. Returns
    (period_key, balances_accrued). Idempotent: a same-period re-run grants 0. The caller commits
    via the uow (D-011)."""
    period = accrual_period_key(frequency, as_of)
    freq_value = AccrualFrequency(frequency).value

    employees = list(
        (
            await session.execute(
                select(Employee.id).where(
                    Employee.tenant_id == tenant_id,
                    Employee.status == EmploymentStatus.ACTIVE.value,
                )
            )
        )
        .scalars()
        .all()
    )
    leave_types = list(
        (
            await session.execute(
                select(LeaveType).where(
                    LeaveType.tenant_id == tenant_id,
                    LeaveType.accrual_frequency == freq_value,
                    LeaveType.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not employees or not leave_types:
        return period, 0

    type_ids = [lt.id for lt in leave_types]
    existing = list(
        (
            await session.execute(
                select(LeaveBalance).where(
                    LeaveBalance.tenant_id == tenant_id,
                    LeaveBalance.employee_id.in_(employees),
                    LeaveBalance.leave_type_id.in_(type_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    by_pair: dict[tuple[uuid.UUID, uuid.UUID], LeaveBalance] = {
        (b.employee_id, b.leave_type_id): b for b in existing
    }

    accrued = 0
    for employee_id in employees:
        for leave_type in leave_types:
            balance = by_pair.get((employee_id, leave_type.id))
            if balance is None:
                # First accrual for this pair: open a balance, grant from zero (capped).
                grant = _capped_grant(Decimal(0), leave_type.accrual_amount, leave_type.max_balance)
                balance = LeaveBalance(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    balance_days=grant,
                    accrued_to_date=grant,
                    taken_to_date=Decimal(0),
                    last_accrual_period=period,
                )
                session.add(balance)
                by_pair[(employee_id, leave_type.id)] = balance
                accrued += 1
                continue
            if balance.last_accrual_period == period:
                # Already accrued for this period — the idempotency guard skips it.
                continue
            grant = _capped_grant(
                balance.balance_days, leave_type.accrual_amount, leave_type.max_balance
            )
            balance.balance_days += grant
            balance.accrued_to_date += grant
            balance.last_accrual_period = period
            accrued += 1
    await session.flush()
    return period, accrued
