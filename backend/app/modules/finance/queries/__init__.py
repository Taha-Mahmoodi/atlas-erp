"""Finance's cross-module read interface (STRUCTURE §5).

Finance is the bottom of the dependency order: every other module (inventory, sales, ...)
may import THIS package to read finance state synchronously, and finance imports no other
module's queries. Keep this surface thin and stable — it is a contract. The journal posting
flow (4.2) calls ``find_period_for_date`` to resolve an entry's period from its posting_date;
inventory/sales call ``get_period_status`` to refuse stock/sales documents dated into a closed
period before they reach the GL.

The single ``queries.py`` reached the 400-line cap, so it split along the §8.4 package rule and the
package kept growing — the read surface now lives in sibling modules, all re-exported here so every
``from app.modules.finance.queries import X`` import keeps working from one surface:

* ``posting_accounts`` — the per-tenant posting-default ACCOUNT resolvers (gr_ir / ppv / ap / ar /
  sales-revenue / wip / production-variance / salary-expense / wages-payable / payroll-tax-payable).
* ``periods`` — the fiscal-period lookups (``find_period_for_date`` / ``get_period_status``).
* ``catalog`` — master-data existence (account / currency / tax code) + FX + the tax engine.
* ``partner_ledger`` — a partner's open AP (vendor bills) / AR (customer invoices) by opaque
  ``partner_id``.
* ``controlling`` — CO dimension validation, cost-centre / project-dimension balances, and the
  statement base aggregates (``account_balances`` / ``net_income``).
* ``dashboards`` — the role-based dashboard KPI aggregates the reporting module (PLAN 13.1, D-058)
  reads downward: ``cash_position`` (sum of is_cash_equivalent balances), ``ar_aging_summary`` /
  ``ap_aging_summary`` (rolled-up bucket totals), ``wip_balance`` (the WIP-clearing balance).

Every function takes an explicit ``tenant_id`` and runs under the caller's tenant context, so
the D-007 filter applies on top of the explicit predicate — these are ordinary tenant-scoped
ORM reads, not a bypass.
"""

from app.modules.finance.queries.catalog import (
    account_exists,
    account_exists_by_id,
    calculate_line_tax,
    currency_exists,
    functional_currency,
    functional_currency_or_none,
    get_rate,
    get_tax_code,
)
from app.modules.finance.queries.controlling import (
    account_balances,
    cost_center_balance,
    cost_center_exists,
    costs_by_project_dimension,
    existing_cost_center_ids,
    existing_profit_center_ids,
    net_income,
    profit_center_exists,
)
from app.modules.finance.queries.dashboards import (
    AgingBuckets,
    ap_aging_summary,
    ar_aging_summary,
    cash_position,
    wip_balance,
)
from app.modules.finance.queries.partner_ledger import (
    customer_open_balance,
    get_open_customer_invoices,
    get_open_vendor_bills,
)
from app.modules.finance.queries.periods import (
    find_period_for_date,
    get_period_status,
)
from app.modules.finance.queries.posting_accounts import (
    ap_control_account,
    ar_control_account,
    gr_ir_clearing_account,
    payroll_tax_payable_account,
    production_variance_account,
    purchase_price_variance_account,
    salary_expense_account,
    sales_revenue_account,
    wages_payable_account,
    wip_clearing_account,
)

__all__ = [
    "AgingBuckets",
    "account_balances",
    "account_exists",
    "account_exists_by_id",
    "ap_aging_summary",
    "ap_control_account",
    "ar_aging_summary",
    "ar_control_account",
    "calculate_line_tax",
    "cash_position",
    "cost_center_balance",
    "cost_center_exists",
    "existing_cost_center_ids",
    "existing_profit_center_ids",
    "costs_by_project_dimension",
    "currency_exists",
    "customer_open_balance",
    "find_period_for_date",
    "functional_currency",
    "functional_currency_or_none",
    "get_open_customer_invoices",
    "get_open_vendor_bills",
    "get_period_status",
    "get_rate",
    "get_tax_code",
    "gr_ir_clearing_account",
    "net_income",
    "payroll_tax_payable_account",
    "production_variance_account",
    "profit_center_exists",
    "purchase_price_variance_account",
    "salary_expense_account",
    "sales_revenue_account",
    "wages_payable_account",
    "wip_balance",
    "wip_clearing_account",
]
