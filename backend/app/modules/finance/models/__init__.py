"""Finance models package (STRUCTURE §3: split into models/ once the combined file passed the
400-line cap). Re-exports every model so ``from app.modules.finance.models import Account`` and
``JournalEntry`` keep working from one surface, and so every importer (alembic env.py, the
tenancy mapper-enumeration suite) registers all tables on ``Base.metadata``.

- ``accounts``: chart of accounts + fiscal years/periods (D-021, D-018).
- ``journal``: the universal journal header + lines (D-017).
- ``fx``: currencies, exchange rates, posting defaults, revaluation runs (D-019).
- ``tax``: configurable line-level tax codes (PLAN 4.4).
"""

from app.modules.finance.models.accounts import (
    Account,
    AccountGroup,
    FiscalPeriod,
    FiscalYear,
)
from app.modules.finance.models.fx import (
    Currency,
    ExchangeRate,
    FxRevaluationRun,
    PostingDefault,
)
from app.modules.finance.models.journal import JournalEntry, JournalLine
from app.modules.finance.models.tax import TaxCode

__all__ = [
    "Account",
    "AccountGroup",
    "Currency",
    "ExchangeRate",
    "FiscalPeriod",
    "FiscalYear",
    "FxRevaluationRun",
    "JournalEntry",
    "JournalLine",
    "PostingDefault",
    "TaxCode",
]
