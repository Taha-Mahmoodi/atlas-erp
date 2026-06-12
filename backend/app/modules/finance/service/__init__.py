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
from app.modules.finance.service.fx import (
    create_currency,
    create_exchange_rate,
    functional_currency,
    get_currency,
    get_rate,
    list_currencies,
    list_exchange_rates,
    set_functional_currency,
)
from app.modules.finance.service.fx_revaluation import (
    list_revaluation_runs,
    run_fx_revaluation,
)
from app.modules.finance.service.journal import (
    create_draft_entry,
    post_entry,
    reverse_entry,
)
from app.modules.finance.service.journal_read import (
    entry_totals,
    get_entry,
    get_entry_with_lines,
    list_entries,
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
from app.modules.finance.service.posting_defaults import (
    get_posting_default,
    list_posting_defaults,
    set_posting_default,
)
from app.modules.finance.service.tax import (
    DocumentTaxSummary,
    TaxCalculation,
    TaxLine,
    calculate_document_tax,
    calculate_line_tax,
    create_tax_code,
    get_tax_code,
    list_tax_codes,
    update_tax_code,
)

__all__ = [
    "DocumentTaxSummary",
    "TaxCalculation",
    "TaxLine",
    "assert_period_closable",
    "calculate_document_tax",
    "calculate_line_tax",
    "close_fiscal_year",
    "close_period",
    "create_account",
    "create_account_group",
    "create_currency",
    "create_draft_entry",
    "create_exchange_rate",
    "create_fiscal_year",
    "create_tax_code",
    "entry_totals",
    "functional_currency",
    "generate_periods",
    "get_account",
    "get_currency",
    "get_entry",
    "get_entry_with_lines",
    "get_posting_default",
    "get_rate",
    "get_tax_code",
    "list_account_groups",
    "list_accounts",
    "list_currencies",
    "list_entries",
    "list_exchange_rates",
    "list_fiscal_periods",
    "list_fiscal_years",
    "list_posting_defaults",
    "list_revaluation_runs",
    "list_tax_codes",
    "open_period",
    "post_entry",
    "reparent_account_group",
    "reverse_entry",
    "run_fx_revaluation",
    "set_functional_currency",
    "set_posting_default",
    "update_account",
    "update_tax_code",
]
