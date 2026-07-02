"""Finance StrEnums (STRUCTURE §7: UPPER_SNAKE values stored as strings) + the
normal-balance mapping. Columns are plain ``sa.String``; services map to/from these classes
(no ``sa.Enum``). Split out of the single constants.py at the 400-line cap (STRUCTURE §8.4),
same package precedent as models/ and service/.
"""

from enum import StrEnum


class AccountType(StrEnum):
    """The five statement-deriving account types (D-021) — all statements project from
    journal lines grouped by the account's type."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class NormalBalance(StrEnum):
    """The side an account normally carries a positive balance on; derivable from
    account_type but stored for query simplicity (D-021)."""

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class CashFlowCategory(StrEnum):
    """Cash-flow-statement bucket (D-021); nullable — only cash-flow accounts carry one."""

    OPERATING = "OPERATING"
    INVESTING = "INVESTING"
    FINANCING = "FINANCING"


class PeriodStatus(StrEnum):
    """Open/closed state of a fiscal year or period (D-018); CLOSED rejects postings dated
    within it — at the service layer and the DB period-posting trigger."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EntryStatus(StrEnum):
    """Journal-entry lifecycle (D-017): DRAFT editable; POSTED immutable (only -> REVERSED,
    with reversed_by set); REVERSED = cancelled by a reversing entry. DB trigger matches."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class DocumentType(StrEnum):
    """Journal-entry document type (D-017): JOURNAL = manual entry; the others tag entries
    from specific flows. A reversal preserves the original's type (FX_REVAL stays FX_REVAL)."""

    JOURNAL = "JOURNAL"
    AP_INVOICE = "AP_INVOICE"
    AR_INVOICE = "AR_INVOICE"
    # The sign-flipped AR_INVOICE: a sales-return credit note (PLAN 7.4) whose journal posts
    # Dr revenue / Dr output tax / Cr AR control — reducing what the customer owes.
    AR_CREDIT_NOTE = "AR_CREDIT_NOTE"
    PAYMENT = "PAYMENT"
    COGS = "COGS"
    FX_REVAL = "FX_REVAL"
    DEPRECIATION = "DEPRECIATION"
    # The consolidated HR-payroll journal (PLAN 10.4): Dr salary-expense by cost centre / Cr
    # payroll-tax-payable / Cr wages-payable, posted from the hr.payroll.posted event (D-055).
    PAYROLL = "PAYROLL"


class TaxDirection(StrEnum):
    """Which side a tax applies to (PLAN 4.4): OUTPUT = charged on a sale, a liability
    posting to ``tax_payable_account_id``; INPUT = paid on a purchase, recoverable, posting
    to ``tax_receivable_account_id``. The calc service picks the account by direction."""

    OUTPUT = "OUTPUT"
    INPUT = "INPUT"


class BillStatus(StrEnum):
    """Vendor-bill lifecycle (PLAN 4.5, AP): DRAFT editable, no number/journal; POSTED has
    number + journal + ``open_amount``; PARTIALLY_PAID/PAID track clearing; REVERSED = journal
    reversed. Open items key on an opaque ``partner_id`` (D-029)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    REVERSED = "REVERSED"


class PaymentStatus(StrEnum):
    """Vendor-payment lifecycle (PLAN 4.5, AP): created+posted in one step (DRAFT transient);
    POSTED has number + clearing journal; REVERSED = journal reversed."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class InvoiceStatus(StrEnum):
    """Customer-invoice lifecycle (PLAN 4.6, AR — BillStatus mirror, sign flipped): DRAFT
    editable; POSTED has number + journal + ``open_amount``; PARTIALLY_PAID/PAID track receipt
    clearing; REVERSED = journal reversed. Open items key on opaque ``partner_id`` (D-029)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    REVERSED = "REVERSED"


class ReceiptStatus(StrEnum):
    """Customer-receipt lifecycle (PLAN 4.6, AR — PaymentStatus mirror): created+posted in
    one step (DRAFT transient); POSTED has number + clearing journal; REVERSED = reversed."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class AllocationBasis(StrEnum):
    """Allocation-rule target weights (PLAN 4.7): PERCENT must sum to 100; FIXED_WEIGHT are
    positive proportional weights. Parts sum EXACTLY via ``core.money.allocate``."""

    PERCENT = "PERCENT"
    FIXED_WEIGHT = "FIXED_WEIGHT"


class AllocationRunStatus(StrEnum):
    """Allocation-run lifecycle (PLAN 4.7): POSTED (numbered redistribution entry with
    cost_center_id per line), REVERSED, or DRAFT (transient)."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class StatementStatus(StrEnum):
    """Bank-statement state (PLAN 4.9), derived from line resolution counts."""

    IMPORTED = "IMPORTED"
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"
    RECONCILED = "RECONCILED"


class LineStatus(StrEnum):
    """Statement-line machine (PLAN 4.9): UNMATCHED -> SUGGESTED -> MATCHED (confirm) or back
    (reject); UNMATCHED -> CLEARED (posted clearing entry). Resolved = MATCHED | CLEARED."""

    UNMATCHED = "UNMATCHED"
    SUGGESTED = "SUGGESTED"
    MATCHED = "MATCHED"
    CLEARED = "CLEARED"


class RateKind(StrEnum):
    """Exchange-rate type (D-019): SPOT = posting-time translation; CLOSING = period-end
    revaluation. get_rate filters on it so the two flows never share a rate."""

    SPOT = "SPOT"
    CLOSING = "CLOSING"


class FxRunStatus(StrEnum):
    """FX revaluation-run status (D-019): COMPLETED once FX_REVAL entries + auto-reversals
    posted; re-running a period REVERSES the prior run (append-only) then posts a fresh
    COMPLETED one; DRAFT is the transient pre-post state."""

    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    REVERSED = "REVERSED"


class DepreciationMethod(StrEnum):
    """How an asset's periodic depreciation is computed (PLAN 4.10): STRAIGHT_LINE spreads
    (cost - salvage) evenly over the useful life (final period absorbs rounding so the total
    is exact); DECLINING_BALANCE takes NBV x annual rate / 12, floored at salvage."""

    STRAIGHT_LINE = "STRAIGHT_LINE"
    DECLINING_BALANCE = "DECLINING_BALANCE"


class AssetStatus(StrEnum):
    """Asset lifecycle (PLAN 4.10): DRAFT editable, no number; ACTIVE numbered at activation
    and selected by depreciation runs; FULLY_DEPRECIATED once accumulated == cost - salvage.
    Disposal/transfer are parity-doc laters — no dead enum values for them."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    FULLY_DEPRECIATED = "FULLY_DEPRECIATED"


class DepreciationRunStatus(StrEnum):
    """Depreciation-run lifecycle (PLAN 4.10, the allocation-run pattern): POSTED (numbered
    run with one grouped journal entry), REVERSED once its entry is reversed, DRAFT transient."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


# account_type -> normal side (D-021): ASSET/EXPENSE debit; LIABILITY/EQUITY/REVENUE credit.
# The service defaults normal_balance from this, so stored value never disagrees with type.
_NORMAL_BALANCE_BY_TYPE: dict[AccountType, NormalBalance] = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
}


def normal_balance_for(account_type: AccountType) -> NormalBalance:
    """The normal balance implied by an account type (D-021); total over the five types."""
    return _NORMAL_BALANCE_BY_TYPE[account_type]
