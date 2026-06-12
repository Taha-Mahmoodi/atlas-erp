"""Finance request/response schemas (Pydantic v2, ApiModel base).

Read schemas mirror the models field-for-field in snake_case; enums are typed with the
constants classes (ApiModel's ``use_enum_values`` serializes them as their UPPER_SNAKE
string, matching how the columns store them). Create/Update carry only the client-settable
fields — ``normal_balance`` is optional on AccountCreate because the service defaults it from
``account_type``; ids, timestamps and tenant_id are server-owned and never accepted.
"""

import uuid
from datetime import date, datetime

from app.core.schemas import ApiModel
from app.modules.finance.constants import (
    AccountType,
    CashFlowCategory,
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
