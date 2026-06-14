"""Reporting (role-based dashboards + report builder) constants (STRUCTURE §3): the dashboard +
report-builder permission keys, the KPI catalog and its KPI→source-permission GATING MAP, and the
report-builder operator / aggregation enums + the 10k row cap (D-009 / D-058 / D-059), registered
into the core RBAC catalog at import.

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
13.1's dashboard + 13.2's report-builder constants sit well under that.

READ-ONLY (D-058 / D-059). Reporting owns NO tables, NO sequences, NO document types — it is a
projection aggregator over OTHER modules' ``queries`` (the dashboard) and a READ-ONLY query builder
over a WHITELIST of their ORM models (the report builder, D-059). The only keys it DECLARES are
``reporting.dashboard.read`` (base dashboard access) and ``reporting.report.run`` (base report
access). Every individual KPI / reportable entity is gated by the SOURCE module's existing read
permission, so both surfaces are ROLE-BASED: a finance role sees finance KPIs + finance reports, a
sales role sees sales ones, etc. (the ``KPI_PERMISSIONS`` map + the registry's per-entity
``source_permission`` are the contracts).
"""

from enum import StrEnum

from app.core.rbac import register_permissions
from app.modules.finance.constants import (
    FINANCE_AP_READ,
    FINANCE_AR_READ,
    FINANCE_STATEMENTS_READ,
)
from app.modules.inventory.constants import INVENTORY_VALUATION_READ
from app.modules.procurement.constants import PROCUREMENT_PO_READ
from app.modules.sales.constants import SALES_ORDER_READ

# --- The base permissions reporting declares (D-009 / D-058 / D-059) ----------
# The price of admission to each surface. Each KPI / reportable entity is then gated by the SOURCE
# module's read permission (KPI_PERMISSIONS below; the registry's per-entity source_permission).
REPORTING_DASHBOARD_READ = "reporting.dashboard.read"
# Base report-builder access (D-059): holding it lets a caller list entities and run/export reports,
# but EACH reportable entity additionally requires its source module's read permission, so a finance
# role can only report on finance entities, etc. (mirrors the dashboard's role-based gating).
REPORTING_REPORT_RUN = "reporting.report.run"

register_permissions(
    REPORTING_DASHBOARD_READ,
    REPORTING_REPORT_RUN,
    descriptions={
        REPORTING_DASHBOARD_READ: "Access the role-based KPI dashboard",
        REPORTING_REPORT_RUN: "Run and export ad-hoc reports over whitelisted entities",
    },
)


# --- Report builder enums + the row cap (D-059, PERFORMANCE §3) ----------------
# The FIXED operator set a report filter may use. A filter names a WHITELISTED column, an operator
# from THIS set, and a value the builder coerces to the column's Python type and BINDS (never
# string-interpolates) — so a value can only ever be data, never SQL (the no-injection guarantee).
class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"  # value is a list; each element coerced + bound
    LIKE = "like"  # case-insensitive substring on string columns only
    BETWEEN = "between"  # value is a [low, high] pair
    IS_NULL = "is_null"  # value is a bool: True → IS NULL, False → IS NOT NULL


# The FIXED aggregation set. COUNT applies to any groupable report; SUM/AVG/MIN/MAX apply only to
# columns the registry marks ``is_aggregatable`` (numeric columns) — validated in the builder.
class Aggregation(StrEnum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


# PERFORMANCE §3: the report builder CAPS result rows at 10k for the JSON grid; anything larger is
# served by the streaming CSV export. The builder fetches CAP + 1 rows to detect+flag truncation.
REPORT_ROW_CAP = 10_000


# --- KPI catalog (D-058) ------------------------------------------------------
# The stable string keys the dashboard response is keyed by. Used by the service (which computes the
# permitted subset) and the schema (typed sub-models per KPI). Plain constants, not an enum, so the
# response-dict keys and the schema field names stay in lockstep with no value translation.
KPI_CASH_POSITION = "cash_position"
KPI_AR_AGING = "ar_aging"
KPI_AP_AGING = "ap_aging"
KPI_INVENTORY_VALUE = "inventory_value"
KPI_OPEN_SALES_ORDERS = "open_sales_orders"
KPI_OPEN_PURCHASE_ORDERS = "open_purchase_orders"
KPI_OTD_PERCENT = "otd_percent"
KPI_WIP_VALUE = "wip_value"


# --- THE KPI → SOURCE-PERMISSION GATING MAP (D-058, the role-based contract) ---
# Each KPI is computed ONLY when the caller holds the SOURCE module's read permission, so the
# dashboard returns only the KPIs the role can see (a finance role gets cash/AR/AP/WIP, a sales role
# gets open orders + OTD, an inventory role gets inventory value, a buyer gets open POs). cash + WIP
# read the same finance statements/journal projection, so both gate on finance.statements.read; AR
# aging on finance.ar.read, AP aging on finance.ap.read (the AP/AR-specific read keys). The service
# iterates this map: gate passes → compute the KPI, else omit it entirely from the response.
KPI_PERMISSIONS: dict[str, str] = {
    KPI_CASH_POSITION: FINANCE_STATEMENTS_READ,
    KPI_AR_AGING: FINANCE_AR_READ,
    KPI_AP_AGING: FINANCE_AP_READ,
    KPI_INVENTORY_VALUE: INVENTORY_VALUATION_READ,
    KPI_OPEN_SALES_ORDERS: SALES_ORDER_READ,
    KPI_OPEN_PURCHASE_ORDERS: PROCUREMENT_PO_READ,
    KPI_OTD_PERCENT: SALES_ORDER_READ,
    # WIP is the finance WIP-clearing balance (D-048/D-058 — the authoritative open-WIP figure),
    # so it gates on the finance statements read, NOT a manufacturing key.
    KPI_WIP_VALUE: FINANCE_STATEMENTS_READ,
}
