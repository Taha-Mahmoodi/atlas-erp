"""Cash-flow statement, indirect method, with a built-in reconciliation self-check (D-021).

Derived entirely from the base aggregate at two points in time — the opening balance (the day BEFORE
``date_from``) and the closing balance (``date_to``) — so it needs no cash tagging on individual
lines. Indirect method: start from net income for the period, then add the signed deltas of every
NON-CASH balance-sheet account (ASSET/LIABILITY/EQUITY that is not a cash equivalent), bucketed by
``cash_flow_category`` (OPERATING/INVESTING/FINANCING).

The self-check (D-021): the net change those movements imply MUST equal the actual movement in the
``is_cash_equivalent`` accounts over the period — the two are forced equal by double-entry (every
debit had a credit). ``is_reconciled`` exposes that identity; ``net_change_from_activities`` and
``cash_account_movement`` expose the cash delta computed both ways so a discrepancy is visible, not
hidden. No stored totals: recomputed from the journal on every read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.finance.constants import AccountType, CashFlowCategory
from app.modules.finance.service.statements.base import (
    ZERO,
    AccountMeta,
    _account_balances,
    load_account_meta,
    net_income_signed,
)

# The non-cash balance-sheet account types whose movement the indirect method walks.
_BALANCE_SHEET_TYPES = (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY)

# Category buckets in presentation order. Accounts with no cash_flow_category on a non-cash
# balance-sheet account fall into OPERATING (the working-capital default).
_CATEGORY_ORDER = (
    CashFlowCategory.OPERATING,
    CashFlowCategory.INVESTING,
    CashFlowCategory.FINANCING,
)


@dataclass(frozen=True)
class CashFlowLine:
    """One account's contribution to a cash-flow category: the cash effect of its balance delta."""

    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


@dataclass
class CashFlowCategorySection:
    """All movements in one OPERATING/INVESTING/FINANCING bucket plus its subtotal (D-021)."""

    category: CashFlowCategory
    lines: list[CashFlowLine] = field(default_factory=list)
    subtotal: Decimal = ZERO


@dataclass
class CashFlowStatement:
    """The indirect cash-flow statement for a period (D-021): net income, the category sections, and
    the reconciliation self-check. ``net_change_from_activities`` is net income plus all section
    subtotals; ``cash_account_movement`` is the independently-measured delta of the cash-equivalent
    accounts; ``is_reconciled`` asserts the two are equal — the universal-journal guarantee."""

    date_from: date
    date_to: date
    net_income: Decimal = ZERO
    sections: list[CashFlowCategorySection] = field(default_factory=list)
    net_change_from_activities: Decimal = ZERO
    cash_account_movement: Decimal = ZERO
    is_reconciled: bool = True


def _cash_effect(account: AccountMeta, delta_signed: Decimal) -> Decimal:
    """The cash effect of a non-cash account's debit-positive balance delta (D-021).

    Cash and a non-cash debit-positive balance move opposite: a RISE in a non-cash asset (debit
    delta up) USES cash, a rise in a liability/equity (credit, debit-positive delta down) PROVIDES
    cash. So the cash effect is the negation of the debit-positive delta for every non-cash
    balance-sheet account, uniformly — which is exactly what makes the sum reconcile to the cash
    accounts' own movement."""
    return -delta_signed


async def cash_flow_indirect(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> CashFlowStatement:
    """The indirect cash-flow statement over ``[date_from, date_to]`` with the reconciliation check.

    Takes opening balances at ``date_from - 1 day`` and closing balances at ``date_to`` from the
    base aggregate, computes net income for the period, walks every non-cash balance-sheet account's
    delta into its ``cash_flow_category`` bucket, and asserts the resulting net change equals the
    cash equivalents' own movement (``is_reconciled``)."""
    opening_to = date_from - timedelta(days=1)
    opening = await _account_balances(session, tenant_id, date_to=opening_to)
    closing = await _account_balances(session, tenant_id, date_to=date_to)
    meta = await load_account_meta(session, tenant_id)

    # Net income for the period = full-history net to close minus full-history net to open.
    net_income = net_income_signed(closing, meta) - net_income_signed(opening, meta)

    sections: dict[CashFlowCategory, CashFlowCategorySection] = {
        category: CashFlowCategorySection(category=category) for category in _CATEGORY_ORDER
    }
    cash_account_movement = ZERO

    account_ids = set(opening) | set(closing) | set(meta)
    for account_id in account_ids:
        account = meta.get(account_id)
        if account is None:
            continue
        delta = closing.get(account_id, ZERO) - opening.get(account_id, ZERO)
        if account.is_cash_equivalent:
            # The independently-measured cash movement (debit-positive: a rise in cash is positive).
            cash_account_movement += delta
            continue
        if account.account_type not in _BALANCE_SHEET_TYPES:
            # Revenue/expense flow through net_income already; only balance-sheet deltas are walked.
            continue
        effect = _cash_effect(account, delta)
        if effect == ZERO:
            continue
        category = account.cash_flow_category or CashFlowCategory.OPERATING
        section = sections[category]
        section.lines.append(
            CashFlowLine(
                account_id=account_id,
                account_code=account.code,
                account_name=account.name,
                amount=effect,
            )
        )
        section.subtotal += effect

    ordered_sections = [sections[category] for category in _CATEGORY_ORDER]
    for section in ordered_sections:
        section.lines.sort(key=lambda line: line.account_code)
    net_change = net_income + sum((s.subtotal for s in ordered_sections), ZERO)

    return CashFlowStatement(
        date_from=date_from,
        date_to=date_to,
        net_income=net_income,
        sections=ordered_sections,
        net_change_from_activities=net_change,
        cash_account_movement=cash_account_movement,
        is_reconciled=net_change == cash_account_movement,
    )
