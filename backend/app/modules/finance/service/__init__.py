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
from app.modules.finance.service.ap_aging import vendor_aging
from app.modules.finance.service.ar_aging import customer_aging
from app.modules.finance.service.customer_invoices import (
    create_customer_invoice,
    get_customer_invoice,
    get_customer_invoice_lines,
    list_customer_invoices,
    post_customer_invoice,
)
from app.modules.finance.service.customer_receipts import (
    create_and_post_receipt,
    get_customer_receipt,
    get_receipt_allocations,
    list_customer_receipts,
)
from app.modules.finance.service.dunning import run_dunning
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
from app.modules.finance.service.vendor_bills import (
    create_vendor_bill,
    get_vendor_bill,
    get_vendor_bill_lines,
    list_vendor_bills,
    post_vendor_bill,
)
from app.modules.finance.service.vendor_payments import (
    create_and_post_payment,
    get_payment_allocations,
    get_vendor_payment,
    list_vendor_payments,
    run_payment_batch,
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
    "create_and_post_payment",
    "create_and_post_receipt",
    "create_currency",
    "create_customer_invoice",
    "create_draft_entry",
    "create_exchange_rate",
    "create_fiscal_year",
    "create_tax_code",
    "create_vendor_bill",
    "customer_aging",
    "entry_totals",
    "functional_currency",
    "generate_periods",
    "get_account",
    "get_currency",
    "get_customer_invoice",
    "get_customer_invoice_lines",
    "get_customer_receipt",
    "get_entry",
    "get_entry_with_lines",
    "get_payment_allocations",
    "get_posting_default",
    "get_rate",
    "get_receipt_allocations",
    "get_tax_code",
    "get_vendor_bill",
    "get_vendor_bill_lines",
    "get_vendor_payment",
    "list_account_groups",
    "list_accounts",
    "list_currencies",
    "list_customer_invoices",
    "list_customer_receipts",
    "list_entries",
    "list_exchange_rates",
    "list_fiscal_periods",
    "list_fiscal_years",
    "list_posting_defaults",
    "list_revaluation_runs",
    "list_tax_codes",
    "list_vendor_bills",
    "list_vendor_payments",
    "open_period",
    "post_customer_invoice",
    "post_entry",
    "post_vendor_bill",
    "reparent_account_group",
    "reverse_entry",
    "run_dunning",
    "run_fx_revaluation",
    "run_payment_batch",
    "set_functional_currency",
    "set_posting_default",
    "update_account",
    "update_tax_code",
    "vendor_aging",
]
