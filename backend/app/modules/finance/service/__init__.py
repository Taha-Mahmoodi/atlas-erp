"""Finance service package (split per STRUCTURE §3: one file per aggregate, each <400 lines).

The router and other callers import service functions from this package surface, so the
split into ``accounts`` (chart of accounts + groups) and ``periods`` (fiscal years +
periods, the D-018 home) is an internal detail. Re-exported here so call sites use one
import (``from app.modules.finance import service`` then ``service.create_account(...)``).
"""

from app.modules.finance.service.accounts import (
    create_account,
    create_account_group,
    get_account,
    list_account_groups,
    list_accounts,
    reparent_account_group,
    update_account,
)
from app.modules.finance.service.periods import (
    assert_period_closable,
    close_fiscal_year,
    close_period,
    create_fiscal_year,
    generate_periods,
    list_fiscal_periods,
    list_fiscal_years,
    open_period,
)

__all__ = [
    "assert_period_closable",
    "close_fiscal_year",
    "close_period",
    "create_account",
    "create_account_group",
    "create_fiscal_year",
    "generate_periods",
    "get_account",
    "list_account_groups",
    "list_accounts",
    "list_fiscal_periods",
    "list_fiscal_years",
    "open_period",
    "reparent_account_group",
    "update_account",
]
