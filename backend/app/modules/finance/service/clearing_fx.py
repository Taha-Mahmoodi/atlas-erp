"""Shared open-item clearing + realized-FX line construction (PLAN 4.6, D-019).

Factored out of AP's ``payment_clearing.py`` so AP (vendor payments) and AR (customer receipts)
share ONE implementation of the realized-FX math instead of duplicating it (the AP clearing was
otherwise AP-specific — it took ``VendorBill`` objects and AP error codes). This file is
engine-agnostic: it works over plain ``ClearedItem`` tuples (control account, the item's gross, the
cleared transaction amount, what earlier entries already cleared, and the functional amount
frozen on the item's control line at posting), so AP passes bills and AR passes invoices through
the same builder.

Realized FX (D-019): the control account was booked at each item's posting-date rate (R1); the bank
moves at the clearing-date rate (R2). ``functional-at-item-rate − functional-at-clearing-rate`` over
each cleared amount is the realized gain/loss, posted to the fx_realized_gain/loss posting-default
account INSIDE the same entry so it balances in functional. When the clearing currency IS the
functional one, R1 == R2 == 1 and there is no FX line. The control side is one-sided by
``control_is_debit`` — AP debits the control to clear (Dr AP), AR credits it (Cr AR) — and the bank
takes the opposite side; the realized-FX line keeps the entry balanced in functional either way.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.core.money import currency_decimals, quantize_money
from app.modules.finance.constants import (
    FX_REALIZED_GAIN,
    FX_REALIZED_LOSS,
    RateKind,
)
from app.modules.finance.models import Account
from app.modules.finance.schemas import JournalLineCreate
from app.modules.finance.service import fx
from app.modules.finance.service.journal_read import load_lines
from app.modules.finance.service.posting_defaults import get_posting_default

# The realized-FX line's descriptions. Constants because they are also how the line is IDENTIFIED
# after posting (``set_fx_line_currency``): it used to be "the third line", which held only while
# every clearing entry had exactly two other lines — an unapplied receipt (D-086) appends a fourth.
FX_GAIN_DESCRIPTION = "Realized FX gain"
FX_LOSS_DESCRIPTION = "Realized FX loss"


@dataclass(frozen=True)
class ClearedItem:
    """One open item a clearing entry settles (PLAN 4.6, D-019). ``control_account_id`` is the AP/AR
    control account booked on the item's posting; ``gross`` is the item's full transaction gross
    (the denominator for its frozen rate); ``cleared`` is the transaction amount this entry settles;
    ``frozen_functional`` is the functional amount the control line carried when the item posted
    (read from its journal line so the rate comes from the actual posting, not a re-lookup);
    ``already_cleared`` is how much of the item EARLIER entries settled (``gross - open_amount``,
    read before this entry draws the balance down), which is what lets the functional draw-down
    telescope instead of re-rating each part (D-088)."""

    control_account_id: uuid.UUID
    gross: Decimal
    cleared: Decimal
    frozen_functional: Decimal
    already_cleared: Decimal


async def require_bank_account(
    session: AsyncSession, tenant_id: uuid.UUID, account_id: uuid.UUID, *, code: str
) -> Account:
    """Validate the bank/cash account exists in this tenant; ``code`` is the caller's 422 error code
    (AP/AR differ) so the message stays module-appropriate."""
    account = (
        await session.execute(
            select(Account).where(Account.tenant_id == tenant_id, Account.id == account_id)
        )
    ).scalar_one_or_none()
    if account is None:
        raise ValidationFailedError(
            message="The bank account does not exist in this tenant",
            code=code,
            details={"account_id": str(account_id)},
        )
    return account


async def frozen_functional_on_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    journal_entry_id: uuid.UUID | None,
    control_account_id: uuid.UUID,
    fallback_gross: Decimal,
    *,
    side: str,
) -> Decimal:
    """The functional amount booked to ``control_account_id`` when the item posted (D-019), read
    from the item's control journal line so the frozen rate comes from the actual posting. ``side``
    is 'credit' for AP (the AP control was credited at posting) or 'debit' for AR (the AR control
    was debited). Falls back to the transaction gross for a single-currency item (func == gross)."""
    lines = await load_lines(session, tenant_id, journal_entry_id)
    for line in lines:
        if line.account_id != control_account_id:
            continue
        functional = (
            line.functional_credit_amount if side == "credit" else line.functional_debit_amount
        )
        if Decimal(str(functional)) > 0:
            return Decimal(str(functional))
    return Decimal(str(fallback_gross))


async def build_clearing_lines(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    items: list[ClearedItem],
    *,
    currency_code: str,
    bank_account_id: uuid.UUID,
    bank_amount: Decimal,
    clearing_date: date,
    partner_id: uuid.UUID,
    control_is_debit: bool,
    control_description: str,
    bank_description: str,
    bank_functional: Decimal | None = None,
) -> tuple[list[JournalLineCreate], list[tuple[Decimal, Decimal]]]:
    """Build the balanced clearing journal lines + their explicit functional (debit, credit) amounts
    (D-019), aligned by index. The control side clears each item at its frozen rate; the bank side
    moves at the clearing-date rate; the realized-FX line absorbs the functional difference so the
    entry balances in functional. ``control_is_debit`` chooses the control's side (AP: Dr control /
    Cr bank; AR: Cr control / Dr bank). The realized-FX line is functional-valued but carries a
    positive transaction side so the per-line one-side CHECK holds (D-017); the entry need not
    balance in TRANSACTION terms (mixed currencies), only in functional — ``create_draft_entry``
    checks the functional sums and ``post_entry`` runs with ``skip_translation``.

    ``bank_functional`` overrides the bank side's functional amount for a caller that is DRAWING
    DOWN a functional balance already booked rather than valuing a fresh cash movement (D-086's
    advance application): re-deriving ``quantize(amount x rate)`` on every draw-down quantizes N
    times against one quantized credit and leaves a residue on the control that never clears.
    ``None`` keeps the cash-movement valuation every other caller wants. The ITEM side telescopes
    for the same reason and needs no flag — see the loop below (#251, D-088)."""
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    func_decimals = currency_decimals(func_code) if func_code else currency_decimals(currency_code)
    is_foreign = func_code is not None and currency_code != func_code

    cleared_total = sum((item.cleared for item in items), Decimal(0))
    control_account_id = items[0].control_account_id

    clearing_rate = (
        await fx.get_rate(
            session, tenant_id, currency_code, func_code, clearing_date, RateKind.SPOT
        )
        if is_foreign
        else Decimal(1)
    )
    func_control = Decimal(0)
    for item in items:
        if is_foreign:
            # TELESCOPE the item's functional, never re-rate it (#251, D-088). The control carries
            # ONE quantized ``frozen_functional`` from the item's posting, so a clearing takes the
            # DIFFERENCE of two quantized cumulatives; the intermediate terms cancel and the last
            # part lands on exactly what was booked. Re-deriving ``quantize(cleared x rate)`` per
            # part instead quantizes N times against that single rounding, and an item settled in
            # SEVERAL parts strands the difference on the AP/AR control forever — silently, because
            # the realized-FX line absorbs it. Same discipline the advance leg already uses.
            item_rate = item.frozen_functional / item.gross
            after = quantize_money((item.already_cleared + item.cleared) * item_rate, func_decimals)
            before = quantize_money(item.already_cleared * item_rate, func_decimals)
            func_control += after - before
        else:
            func_control += item.cleared
    func_bank = (
        quantize_money(bank_amount * clearing_rate, func_decimals)
        if bank_functional is None
        else bank_functional
    )

    control_line = JournalLineCreate(
        account_id=control_account_id,
        description=control_description,
        transaction_debit_amount=cleared_total if control_is_debit else Decimal(0),
        transaction_credit_amount=Decimal(0) if control_is_debit else cleared_total,
        partner_id=partner_id,
    )
    bank_line = JournalLineCreate(
        account_id=bank_account_id,
        description=bank_description,
        transaction_debit_amount=Decimal(0) if control_is_debit else bank_amount,
        transaction_credit_amount=bank_amount if control_is_debit else Decimal(0),
    )
    lines: list[JournalLineCreate] = [control_line, bank_line]
    functional_amounts: list[tuple[Decimal, Decimal]] = (
        [(func_control, Decimal(0)), (Decimal(0), func_bank)]
        if control_is_debit
        else [(Decimal(0), func_control), (func_bank, Decimal(0))]
    )

    fx_line = await _fx_line(
        session, tenant_id, func_control, func_bank, control_is_debit=control_is_debit
    )
    if fx_line is not None:
        line, funcs = fx_line
        lines.append(line)
        functional_amounts.append(funcs)
    return lines, functional_amounts


async def _fx_line(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    func_control: Decimal,
    func_bank: Decimal,
    *,
    control_is_debit: bool,
) -> tuple[JournalLineCreate, tuple[Decimal, Decimal]] | None:
    """The realized-FX line, when the control and bank functional sides differ, else None (D-019).
    It is APPENDED last, and is found after posting by its description rather than its position —
    an unapplied receipt (D-086) posts a fourth line, so "the third line" stopped being true. The
    line balances the entry in functional and carries a positive transaction side equal to its
    functional amount so the per-line one-side CHECK holds (D-017).

    For AP (control debit): realized = func_control − func_bank; positive means AP owed MORE than
    paid -> a GAIN (credit). For AR (control credit): realized = func_bank − func_control; positive
    means cash received exceeds the receivable booked -> a GAIN (credit). Either way a positive
    realized is a credit, a negative a debit, and the entry balances."""
    realized = (func_control - func_bank) if control_is_debit else (func_bank - func_control)
    if realized == 0:
        return None
    amount = abs(realized)
    purpose = FX_REALIZED_GAIN if realized > 0 else FX_REALIZED_LOSS
    fx_account_id = await get_posting_default(session, tenant_id, purpose)
    if realized > 0:
        line = JournalLineCreate(
            account_id=fx_account_id,
            description=FX_GAIN_DESCRIPTION,
            transaction_credit_amount=amount,
        )
        return line, (Decimal(0), amount)
    line = JournalLineCreate(
        account_id=fx_account_id,
        description=FX_LOSS_DESCRIPTION,
        transaction_debit_amount=amount,
    )
    return line, (amount, Decimal(0))


async def set_fx_line_currency(
    session: AsyncSession, tenant_id: uuid.UUID, entry_id: uuid.UUID
) -> None:
    """Denominate the realized-FX line (if any) in the functional currency (D-019) — it is a
    functional gain/loss, not a foreign cash flow. Cosmetic vs the entry currency on the line;
    mutate the loaded object so the change is captured. No-op when no FX line exists.

    The line is found by the description ``_fx_line`` gave it, not by position: "the third line"
    was true only while a clearing entry was exactly control + bank + FX, and an unapplied customer
    receipt (D-086) posts a fourth. Same two queries either way."""
    func_code = await fx.functional_currency_or_none(session, tenant_id)
    if func_code is None:
        return
    lines = await load_lines(session, tenant_id, entry_id)
    for line in lines:
        if line.description in (FX_GAIN_DESCRIPTION, FX_LOSS_DESCRIPTION):
            line.currency_code = func_code
            await session.flush()
            return
