"""Reporting module (PLAN 13.1, the FIRST Phase 13 plan) — role-based dashboard KPI cards.

PLAN 13.1 delivers the deliberately small reporting core the build spec §13.1 scopes: ROLE-BASED
DASHBOARDS with KPI cards — cash position, AR/AP aging, inventory value, open orders, OTD%, WIP.
(The generic report builder is §13.2, the next plan.)

THE LOAD-BEARING IDEA — A READ-ONLY KPI AGGREGATOR (D-058, D-021). Reporting owns NO tables, NO
sequences, NO document types: every KPI is a PROJECTION read off another module's existing
``queries`` — never a new stored total (D-021: reports are projections; KPIs read existing queries).
Reporting is the NEWEST module and the TOP of the dependency order, so it imports ONLY other
modules' ``queries`` (downward reads), never their ``service``/``models`` (STRUCTURE §5). finance,
inventory, sales, procurement, manufacturing are all OLDER and import nothing from reporting —
one-directional, NO cycle (verified, D-058).

ROLE-BASED GATING (D-058 / D-009). The dashboard is role-based: each KPI is gated by the SOURCE
module's read permission (the ``KPI_PERMISSIONS`` map in ``constants.py``). The single dashboard
endpoint returns ONLY the KPIs the caller is permitted to see — a finance role gets cash / AR / AP /
WIP, a sales role gets open sales orders + OTD, an inventory role gets inventory value, a buyer gets
open POs. The base key ``reporting.dashboard.read`` is the price of admission to the endpoint; the
per-KPI source keys decide what comes back.

THE KPI → SOURCE-QUERY MAP (D-058).

- ``cash_position``       → ``finance/queries.cash_position`` (Σ is_cash_equivalent balances).
- ``ar_aging``           → ``finance/queries.ar_aging_summary`` (bucket totals over open invoices).
- ``ap_aging``           → ``finance/queries.ap_aging_summary`` (bucket totals over open bills).
- ``inventory_value``    → ``inventory/queries.valuation_summary`` (Σ inv_item_valuations.
  total_value + FIFO live layers, summed in the service).
- ``open_sales_orders``  → ``sales/queries.open_sales_orders`` (count + Σ value, confirmed-undeliv).
- ``open_purchase_orders`` → ``procurement/queries.open_purchase_orders`` (count + Σ value, open
  POs).
- ``otd_percent``        → ``sales/queries.on_time_delivery`` (simple delivery-vs-requested OTD).
- ``wip_value``          → ``finance/queries.wip_balance`` (the WIP-clearing balance — the
  authoritative open-WIP figure, D-048).

THE SINGLE-CALL DASHBOARD (PERFORMANCE §4 / §6). The CLIENT makes ONE call to
``GET /api/v1/reporting/dashboard``, which internally runs a FIXED, BOUNDED set of KPI aggregates
(N aggregates for N permitted KPIs — each O(1), never N+1). So PERFORMANCE §4's "one screen ≤ 3
calls" holds: the dashboard screen is a single endpoint call. The internal aggregate count exceeds 3
(many KPIs) by design — documented, asserted with the query counter (D-058).

NO events / handlers (D-058): reporting triggers no cross-module write — it is a pure read
aggregator (an empty event file would be a dead file, STRUCTURE §8.3). NO migration: it owns no
tables.

Structure (each <400 lines, STRUCTURE §3): ``constants.py`` (the dashboard key + KPI→permission
map), ``schemas.py`` (the typed KPI sub-models), ``service.py`` (``dashboard_kpis``), ``router.py``
(the single dashboard endpoint). No ``queries.py`` — reporting is a LEAF consumer; nothing reads it,
so an empty queries file would be an orphan (STRUCTURE §8.3).
"""
