"""Reporting (role-based dashboards) constants (STRUCTURE §3): the dashboard permission key + the
KPI catalog and its KPI→source-permission GATING MAP, registered into the core RBAC catalog at
import (D-009 / D-058).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
13.1's read-only KPI dashboard sits well under that.

READ-ONLY (D-058). Reporting owns NO tables, NO sequences, NO document types — it is a projection
aggregator over OTHER modules' ``queries`` (D-021: KPIs read existing queries, never new stored
totals). So the only key it DECLARES is ``reporting.dashboard.read`` (base dashboard access). Every
individual KPI is gated by the SOURCE module's existing read permission, so the dashboard is
ROLE-BASED: a finance role sees finance KPIs, a sales role sees sales KPIs, and the endpoint returns
ONLY the KPIs the caller is permitted to see (the ``KPI_PERMISSIONS`` map below is the contract).
"""

from app.core.rbac import register_permissions
from app.modules.finance.constants import (
    FINANCE_AP_READ,
    FINANCE_AR_READ,
    FINANCE_STATEMENTS_READ,
)
from app.modules.inventory.constants import INVENTORY_VALUATION_READ
from app.modules.procurement.constants import PROCUREMENT_PO_READ
from app.modules.sales.constants import SALES_ORDER_READ

# --- The base dashboard permission (D-009 / D-058) ----------------------------
# The ONLY key reporting declares: holding it is the price of admission to the dashboard endpoint.
# Each KPI inside is then gated by the SOURCE module's read permission (KPI_PERMISSIONS below).
REPORTING_DASHBOARD_READ = "reporting.dashboard.read"

register_permissions(
    REPORTING_DASHBOARD_READ,
    descriptions={
        REPORTING_DASHBOARD_READ: "Access the role-based KPI dashboard",
    },
)


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
