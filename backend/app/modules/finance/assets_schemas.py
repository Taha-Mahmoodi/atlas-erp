"""Asset accounting request/response schemas (PLAN 4.10, Pydantic v2, ApiModel base).

A sibling of ``schemas.py`` exactly like ``bank_schemas.py``/``payables_schemas.py``
(STRUCTURE §8.5 one-concept-per-file; ``schemas.py`` is at the cap). Money fields are
``Decimal`` serialized as strings (D-015). Server-owned fields (ids, asset_number, status,
capitalized_journal_entry_id, run bookkeeping, timestamps) are never accepted on requests.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.finance.constants import DepreciationMethod


class AssetCreate(ApiModel):
    """Create a DRAFT asset. ``declining_rate_percent`` (annual %, e.g. 20 = 20%/yr) is
    required when the method is DECLINING_BALANCE and rejected otherwise; salvage must be
    below cost. ``currency_code`` defaults to the tenant's functional currency."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    acquisition_date: date
    acquisition_cost: Decimal = Field(gt=0)
    salvage_value: Decimal = Field(default=Decimal(0), ge=0)
    useful_life_months: int = Field(ge=1)
    depreciation_method: DepreciationMethod
    declining_rate_percent: Decimal | None = None
    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class AssetUpdate(ApiModel):
    """Patch a DRAFT asset (409 once activated). Omitted fields stay unchanged; the service
    re-validates the resulting combination (method/rate pairing, salvage < cost, accounts)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    acquisition_date: date | None = None
    acquisition_cost: Decimal | None = Field(default=None, gt=0)
    salvage_value: Decimal | None = Field(default=None, ge=0)
    useful_life_months: int | None = Field(default=None, ge=1)
    depreciation_method: DepreciationMethod | None = None
    declining_rate_percent: Decimal | None = None
    asset_account_id: uuid.UUID | None = None
    accumulated_depreciation_account_id: uuid.UUID | None = None
    depreciation_expense_account_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None


class AssetActivateRequest(ApiModel):
    """Activate a DRAFT asset (claims the AST number). ``capitalize=True`` additionally posts
    the acquisition journal (Dr asset account / Cr acquisition clearing); ``False`` just
    activates — for assets entered with opening balances already on the books."""

    capitalize: bool = False


class AssetRead(ApiModel):
    id: uuid.UUID
    asset_number: str | None = None
    name: str
    description: str | None = None
    acquisition_date: date
    acquisition_cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    depreciation_method: str
    declining_rate_percent: Decimal | None = None
    status: str
    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID
    cost_center_id: uuid.UUID | None = None
    currency_code: str
    capitalized_journal_entry_id: uuid.UUID | None = None
    created_at: datetime


class DepreciationRunRequest(ApiModel):
    """Run depreciation for one fiscal period. ``run_date`` must fall inside the period (the
    posted entry's date) and the period must be OPEN."""

    fiscal_period_id: uuid.UUID
    run_date: date


class DepreciationRunRead(ApiModel):
    id: uuid.UUID
    run_number: str | None = None
    fiscal_period_id: uuid.UUID
    run_date: date
    status: str
    journal_entry_id: uuid.UUID | None = None
    total_amount: Decimal
    asset_count: int
    created_at: datetime


class DepreciationEntryRead(ApiModel):
    id: uuid.UUID
    run_id: uuid.UUID
    asset_id: uuid.UUID
    fiscal_period_id: uuid.UUID
    amount: Decimal
    accumulated_after: Decimal
    nbv_after: Decimal


class AssetRegisterRow(ApiModel):
    """One asset in the register projection: accumulated/NBV are RECOMPUTED from the
    depreciation entries as of the report date — no stored totals (D-021 spirit)."""

    asset_id: uuid.UUID
    asset_number: str | None = None
    name: str
    status: str
    currency_code: str
    acquisition_cost: Decimal
    accumulated_depreciation: Decimal
    net_book_value: Decimal


class AssetRegisterReport(ApiModel):
    as_of: date
    items: list[AssetRegisterRow]
