"""Domain events HR PUBLISHES (D-011/D-055) — HR's FIRST cross-module event.

Declarative data only — no logic, no models — so finance's ``handlers.py`` may import these typed
classes (the STRUCTURE §5 events.py allowance: an event carries no behaviour, so a subscriber in
another module imports it without any logic).

``PayrollPosted`` is the SANCTIONED cross-module mechanism for the payroll-run →
consolidated-journal effect (D-055), the MIRROR of the 6.4 invoice-match → AP-bill and 7.4
sales-billing → AR-invoice
precedents. HR OWNS the payroll run; it MUST NOT call finance's service directly (STRUCTURE §5
forbids importing another module's service). So a payroll POST publishes this event carrying
everything finance needs to post ONE consolidated journal — the resolved salary-expense /
payroll-tax-payable / wages-payable account ids (HR read them from ``finance/queries`` before
publishing), the run totals, and the per-cost-centre salary-expense allocation so the Dr legs carry
the CO cost-centre dimension. Finance's ``create_payroll_journal`` subscribes, posts the journal via
the finance posting service (NOT raw inserts) dated ``pay_date``, and links payroll-run → 'posts' →
journal. The handler shares the session, so the journal lands in the SAME transaction as the run's
POSTED flip — all-or-nothing (D-011): a closed period at ``pay_date`` or any handler failure rolls
the WHOLE post back.

THE BALANCING INVARIANT (D-055): ``total_gross == total_tax + total_net``, so the journal balances
(Dr salary-expense total_gross / Cr payroll-tax-payable total_tax + Cr wages-payable total_net). The
salary-expense Dr is SPLIT per cost centre (``salary_by_cost_center``) so labour cost is
attributable in CO; the tax + net legs are single consolidated credits.
"""

import uuid
from decimal import Decimal
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.core.events import DomainEvent
from app.modules.hr.constants import PAYROLL_POSTED_EVENT_KEY


class PayrollCostCenterExpense(BaseModel):
    """One cost-centre's salary-expense allocation (D-055), the payload finance's handler turns into
    a salary-expense Dr line carrying that cost-centre dimension. Plain frozen data: the nullable
    OPAQUE finance cost-centre id (D-029 — ``None`` is the unallocated bucket, posted with no
    cost-centre dimension) and the summed gross salary for employees in that cost centre. The sum of
    every ``amount`` equals the run's total gross (the Dr side of the balanced journal)."""

    model_config = ConfigDict(frozen=True)

    cost_center_id: uuid.UUID | None
    amount: Decimal


class PayrollPosted(DomainEvent):
    """A payroll run was posted (PLAN 10.4, D-055). Finance's ``create_payroll_journal`` subscribes
    and posts the consolidated payroll journal in the SAME transaction: Dr salary-expense by cost
    centre (total gross) / Cr payroll-tax-payable (total tax) / Cr wages-payable (total net) —
    balanced because ``total_gross == total_tax + total_net``. HR PUBLISHES; finance handles its OWN
    journal posting (HR must not import finance/service — STRUCTURE §5).

    - ``payroll_run_id`` + ``run_number`` + ``document_id`` — the run document (``document_id`` is
      the core_documents id finance links the journal document to, via the 'posts' edge).
    - ``pay_date`` — the posting date the journal lands on (ISO date string); a date in a CLOSED
      period makes the journal trip the period trigger here, rolling the whole post back.
    - ``currency_code`` — the run's transaction currency the journal posts in.
    - ``total_gross`` / ``total_tax`` / ``total_net`` — the consolidated leg amounts (gross = tax +
      net).
    - ``salary_expense_account_id`` — the salary-expense (EXPENSE) account the Dr legs hit (resolved
      from finance by HR before publishing).
    - ``payroll_tax_payable_account_id`` — the payroll-tax-payable (LIABILITY) account the tax Cr
      leg hits.
    - ``wages_payable_account_id`` — the wages-payable (LIABILITY) account the net Cr leg hits.
    - ``salary_by_cost_center`` — the per-cost-centre salary-expense allocation (see
      ``PayrollCostCenterExpense``); each becomes a Dr line carrying its cost-centre dimension."""

    key: ClassVar[str] = PAYROLL_POSTED_EVENT_KEY

    payroll_run_id: uuid.UUID
    run_number: str
    document_id: uuid.UUID
    pay_date: str
    currency_code: str
    total_gross: Decimal
    total_tax: Decimal
    total_net: Decimal
    salary_expense_account_id: uuid.UUID
    payroll_tax_payable_account_id: uuid.UUID
    wages_payable_account_id: uuid.UUID
    salary_by_cost_center: tuple[PayrollCostCenterExpense, ...]


__all__ = ["PayrollCostCenterExpense", "PayrollPosted"]
