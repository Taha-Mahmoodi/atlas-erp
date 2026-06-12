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
from app.modules.finance.service.allocation import (
    get_allocation_run,
    list_allocation_runs,
    run_allocation,
)
from app.modules.finance.service.allocation_rules import (
    create_allocation_rule,
    get_allocation_rule,
    get_rule_targets,
    list_allocation_rules,
    update_allocation_rule,
)
from app.modules.finance.service.ap_aging import vendor_aging
from app.modules.finance.service.ar_aging import customer_aging
from app.modules.finance.service.bank_import import (
    get_bank_statement,
    import_statement,
    list_bank_statements,
    list_statement_lines,
    refresh_statement_status,
    statement_progress,
)
from app.modules.finance.service.bank_reconcile import (
    clear_unmatched_line,
    confirm_match,
    reject_suggestion,
    suggest_matches,
)
from app.modules.finance.service.controlling import (
    create_cost_center,
    create_profit_center,
    get_cost_center,
    get_profit_center,
    list_cost_centers,
    list_profit_centers,
    update_cost_center,
    update_profit_center,
)
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
from app.modules.finance.service.statements import (
    balance_sheet,
    cash_flow_indirect,
    cost_center_report,
    margin_by_product,
    profit_and_loss,
    trial_balance,
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
    "assert_period_closable",
    "balance_sheet",
    "calculate_document_tax",
    "calculate_line_tax",
    "cash_flow_indirect",
    "clear_unmatched_line",
    "close_fiscal_year",
    "close_period",
    "confirm_match",
    "cost_center_report",
    "create_account",
    "create_account_group",
    "create_allocation_rule",
    "create_and_post_payment",
    "create_and_post_receipt",
    "create_cost_center",
    "create_currency",
    "create_customer_invoice",
    "create_draft_entry",
    "create_exchange_rate",
    "create_fiscal_year",
    "create_profit_center",
    "create_tax_code",
    "create_vendor_bill",
    "customer_aging",
    "DocumentTaxSummary",
    "entry_totals",
    "functional_currency",
    "generate_periods",
    "get_account",
    "get_allocation_rule",
    "get_allocation_run",
    "get_bank_statement",
    "get_cost_center",
    "get_currency",
    "get_customer_invoice",
    "get_customer_invoice_lines",
    "get_customer_receipt",
    "get_entry",
    "get_entry_with_lines",
    "get_payment_allocations",
    "get_posting_default",
    "get_profit_center",
    "get_rate",
    "get_receipt_allocations",
    "get_rule_targets",
    "get_tax_code",
    "get_vendor_bill",
    "get_vendor_bill_lines",
    "get_vendor_payment",
    "import_statement",
    "list_account_groups",
    "list_accounts",
    "list_allocation_rules",
    "list_allocation_runs",
    "list_bank_statements",
    "list_cost_centers",
    "list_currencies",
    "list_customer_invoices",
    "list_customer_receipts",
    "list_entries",
    "list_exchange_rates",
    "list_fiscal_periods",
    "list_fiscal_years",
    "list_posting_defaults",
    "list_profit_centers",
    "list_revaluation_runs",
    "list_statement_lines",
    "list_tax_codes",
    "list_vendor_bills",
    "list_vendor_payments",
    "margin_by_product",
    "open_period",
    "post_customer_invoice",
    "post_entry",
    "post_vendor_bill",
    "profit_and_loss",
    "refresh_statement_status",
    "reject_suggestion",
    "reparent_account_group",
    "reverse_entry",
    "run_allocation",
    "run_dunning",
    "run_fx_revaluation",
    "run_payment_batch",
    "set_functional_currency",
    "set_posting_default",
    "statement_progress",
    "suggest_matches",
    "TaxCalculation",
    "TaxLine",
    "trial_balance",
    "update_account",
    "update_allocation_rule",
    "update_cost_center",
    "update_profit_center",
    "update_tax_code",
    "vendor_aging",
]
