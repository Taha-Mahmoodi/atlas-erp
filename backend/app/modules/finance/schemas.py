"""Finance request/response schemas (Pydantic v2, ApiModel base).

Read schemas mirror the models field-for-field in snake_case; enums are typed with the
constants classes (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE
string, matching how the columns store them). Create/Update carry only the client-settable
fields — ``normal_balance`` is optional on AccountCreate because the service defaults it from
``account_type``; ids, timestamps and tenant_id are server-owned and never accepted.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.finance.constants import (
    AccountType,
    CashFlowCategory,
    DocumentType,
    EntryStatus,
    NormalBalance,
    PeriodStatus,
)

# --- Accounts -----------------------------------------------------------------


class AccountCreate(ApiModel):
    code: str
    name: str
    account_type: AccountType
    # Optional: defaulted from account_type by the service when omitted (D-021).
    normal_balance: NormalBalance | None = None
    is_postable: bool = True
    cash_flow_category: CashFlowCategory | None = None
    is_cash_equivalent: bool = False
    account_group_id: uuid.UUID | None = None
    is_active: bool = True


class AccountUpdate(ApiModel):
    """Partial update — every field optional; code and account_type are immutable after
    creation (a posted account's type/code would invalidate historical projections), so
    they are deliberately absent from this schema."""

    name: str | None = None
    normal_balance: NormalBalance | None = None
    is_postable: bool | None = None
    cash_flow_category: CashFlowCategory | None = None
    is_cash_equivalent: bool | None = None
    account_group_id: uuid.UUID | None = None
    is_active: bool | None = None


class AccountRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    is_postable: bool
    cash_flow_category: CashFlowCategory | None
    is_cash_equivalent: bool
    account_group_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountFilter(ApiModel):
    """List filters for the accounts endpoint. None means "no constraint"; the router folds
    the set into the cursor's filter fingerprint so a cursor cannot cross filtered views."""

    account_type: AccountType | None = None
    is_postable: bool | None = None
    is_active: bool | None = None
    account_group_id: uuid.UUID | None = None


# --- Account groups -----------------------------------------------------------


class AccountGroupCreate(ApiModel):
    code: str
    name: str
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class AccountGroupRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


# --- Fiscal years / periods ---------------------------------------------------


class FiscalYearCreate(ApiModel):
    """Create a fiscal year. ``period_count`` periods of roughly equal calendar months are
    generated from start_date by the service (default 12); the year's end_date is set to the
    last generated period's end so the periods exactly tile the year (D-018)."""

    code: str
    name: str
    start_date: date
    period_count: int = 12


class FiscalYearRead(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    start_date: date
    end_date: date
    status: PeriodStatus
    created_at: datetime
    updated_at: datetime


class FiscalPeriodRead(ApiModel):
    id: uuid.UUID
    fiscal_year_id: uuid.UUID
    period_number: int
    name: str
    start_date: date
    end_date: date
    status: PeriodStatus
    created_at: datetime
    updated_at: datetime


class PeriodStatusUpdate(ApiModel):
    """Body for the open/close action endpoints — the target status. The router exposes
    ``/close`` and ``/open`` action sub-resources that set this; the schema makes the
    transition explicit and auditable."""

    status: PeriodStatus


# --- Journal entries (D-017) --------------------------------------------------
# Money fields are Decimal in Python, serialized as strings (D-015); the client types them as
# string and formats in lib/format.ts. For v1 the caller supplies only transaction amounts;
# functional amounts equal them (single functional currency, FX in 4.3).


class JournalLineCreate(ApiModel):
    """One line on a draft entry. Exactly one of debit/credit is positive (the other defaults to
    0); the service mirrors the DB one-side CHECK and rejects a two-sided line. Dimensions are
    optional ids stored on the line for later projection/linkage."""

    account_id: uuid.UUID
    description: str | None = None
    transaction_debit_amount: Decimal = Decimal(0)
    transaction_credit_amount: Decimal = Decimal(0)
    cost_center_id: uuid.UUID | None = None
    profit_center_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    partner_type: str | None = None
    partner_id: uuid.UUID | None = None


class JournalEntryCreate(ApiModel):
    """Create a DRAFT entry with >= 2 balanced one-sided lines (D-017). ``document_type`` defaults
    to JOURNAL. ``currency_code`` is the single transaction currency for the whole entry."""

    posting_date: date
    currency_code: str
    description: str | None = None
    document_type: DocumentType = DocumentType.JOURNAL
    lines: list[JournalLineCreate]


class JournalEntryReverseRequest(ApiModel):
    """Reverse a posted entry into ``reversal_date`` (must fall in an open period). The reversing
    entry copies each line with debit/credit swapped and claims its own number (D-017)."""

    reversal_date: date
    description: str | None = None


class JournalLineRead(ApiModel):
    id: uuid.UUID
    line_number: int
    account_id: uuid.UUID
    description: str | None
    transaction_debit_amount: Decimal
    transaction_credit_amount: Decimal
    functional_debit_amount: Decimal
    functional_credit_amount: Decimal
    currency_code: str
    cost_center_id: uuid.UUID | None
    profit_center_id: uuid.UUID | None
    project_id: uuid.UUID | None
    item_id: uuid.UUID | None
    partner_type: str | None
    partner_id: uuid.UUID | None
    is_posted: bool
    posting_date: date | None
    fiscal_period_id: uuid.UUID | None


class JournalEntryRead(ApiModel):
    """Entry header without lines — the list-row shape."""

    id: uuid.UUID
    entry_number: str | None
    posting_date: date
    fiscal_period_id: uuid.UUID | None
    document_type: DocumentType
    currency_code: str
    description: str | None
    status: EntryStatus
    reverses_entry_id: uuid.UUID | None
    reversed_by_entry_id: uuid.UUID | None
    posted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JournalEntryDetail(JournalEntryRead):
    """Entry header WITH its lines — the GET /{id} shape."""

    lines: list[JournalLineRead]
