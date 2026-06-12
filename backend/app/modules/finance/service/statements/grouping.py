"""Shared presentation-grouping for the P&L and balance sheet (D-021).

Both statements present accounts under the ``fin_account_groups`` hierarchy with a subtotal per
group, then a section total. This is pure presentation over the base aggregate — the grouping never
changes a balance, only how balances are laid out — so the P&L and balance sheet share it rather
than each re-deriving group subtotals slightly differently.

Accounts with no group fall under a synthetic ``(ungrouped)`` bucket so nothing is silently dropped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.modules.finance.service.statements.base import (
    ZERO,
    AccountMeta,
    presentation_amount,
)

# Sentinel group code/name for accounts that hang off no group node.
_UNGROUPED_CODE = "(ungrouped)"
_UNGROUPED_NAME = "Ungrouped"


@dataclass(frozen=True)
class StatementLine:
    """One account on a grouped statement: its code/name and presentation-signed amount."""

    account_id: uuid.UUID
    account_code: str
    account_name: str
    amount: Decimal


@dataclass
class StatementGroup:
    """A presentation group with its accounts and their subtotal (D-021)."""

    group_code: str
    group_name: str
    lines: list[StatementLine] = field(default_factory=list)
    subtotal: Decimal = ZERO


def group_accounts(
    balances: dict[uuid.UUID, Decimal],
    meta: dict[uuid.UUID, AccountMeta],
    account_ids: set[uuid.UUID],
) -> tuple[list[StatementGroup], Decimal]:
    """Lay ``account_ids`` out under their presentation groups with per-group subtotals (D-021).

    Each account's signed base balance is re-signed via ``presentation_amount`` to its natural
    magnitude (revenue positive, liability positive, ...), then bucketed by its group. Accounts that
    net to zero are omitted; accounts with no group fall under the ``(ungrouped)`` bucket. Returns
    the groups (sorted by group code, lines sorted by account code) and the section total — the sum
    of every included account's presentation amount, which the caller asserts against."""
    buckets: dict[str, StatementGroup] = {}
    section_total = ZERO
    for account_id in account_ids:
        account = meta.get(account_id)
        if account is None:
            continue
        amount = presentation_amount(account, balances.get(account_id, ZERO))
        if amount == ZERO:
            continue
        code = account.group_code or _UNGROUPED_CODE
        name = account.group_name or _UNGROUPED_NAME
        bucket = buckets.get(code)
        if bucket is None:
            bucket = StatementGroup(group_code=code, group_name=name)
            buckets[code] = bucket
        bucket.lines.append(
            StatementLine(
                account_id=account_id,
                account_code=account.code,
                account_name=account.name,
                amount=amount,
            )
        )
        bucket.subtotal += amount
        section_total += amount

    groups = sorted(buckets.values(), key=lambda g: g.group_code)
    for group in groups:
        group.lines.sort(key=lambda line: line.account_code)
    return groups, section_total
