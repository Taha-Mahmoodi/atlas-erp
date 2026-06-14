# Reporting (`backend/app/modules/reporting/`)

Reporting is the **eleventh module** (PLAN 13.1), the **role-based dashboard** layer, sitting at the
**top of the dependency order** (STRUCTURE §5 / **D-058**). PLAN 13.1 delivers the build-spec §13.1
scope: **role-based dashboards with KPI cards** — cash position, AR/AP aging, inventory value, open
sales/purchase orders, OTD%, WIP. (The generic report builder is §13.2, the next plan.)

The normative design lives in [docs/architecture.md](../architecture.md) (D-021 statements/CO as
projections — KPIs read existing queries, never new stored totals; D-007 tenancy; D-009 RBAC; D-014
error envelope; D-015 money types; D-048 WIP-clearing) and the **D-058** decision in
[DECISIONS.md](../../DECISIONS.md); this guide is the operator/contributor map.

## Status

**PLAN 13.1 is COMPLETE** — this OPENS Phase 13 (Reporting). The single role-based dashboard endpoint
returns each role's KPI cards.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `reporting.dashboard.read` (base key, registered at import) + the KPI catalog + the `KPI_PERMISSIONS` gating map | D-058, D-009 |
| `schemas.py` | `MoneyKpi` / `AgingSummary` / `CountValueKpi` / `OtdKpi` sub-models + the optional-field `DashboardResponse`; money as strings | D-015 |
| `service.py` | `dashboard_kpis(session, tenant_id, permissions, *, as_of)` — computes only the permitted KPIs off the source queries | D-058, D-021 |
| `router.py` | `GET /api/v1/reporting/dashboard` (the single bundle endpoint, base-permission-guarded) | D-009 |

**No `models.py`, no migration, no `queries.py`, no `events.py`/`handlers.py`.** Reporting owns **no
tables** (read-only over existing tables), is a **leaf consumer** (nothing imports it, so a
`queries.py` would be an orphan — STRUCTURE §8.3), and triggers **no cross-module write** (an empty
event file would be a dead file). **No migration was needed** — latest migration stays **0042**.

## The read-only KPI aggregator (the load-bearing idea)

Every KPI is a **projection** read off another module's existing `queries` — never a new stored total
(**D-021**: reports are projections; KPIs read existing queries). Reporting is the **newest** module
and the **top** of the dependency order, so it imports **only** other modules' `queries` (downward
reads), **never** their `service`/`models` (STRUCTURE §5). finance, inventory, sales, procurement and
manufacturing are all **older** and import nothing from reporting → **one-directional, no cycle**.

## The KPI → source-query map

| KPI | Schema | Source query | Notes |
|---|---|---|---|
| `cash_position` | `MoneyKpi` | `finance/queries.cash_position` | Σ presentation balance of `is_cash_equivalent` accounts over the posted journal |
| `ar_aging` | `AgingSummary` | `finance/queries.ar_aging_summary` | rolled-up bucket totals over open customer invoices (61-90 + over-90 folded into 90+) |
| `ap_aging` | `AgingSummary` | `finance/queries.ap_aging_summary` | rolled-up bucket totals over open vendor bills |
| `inventory_value` | `MoneyKpi` | `inventory/queries.valuation_summary` | Σ `inv_item_valuations.total_value` + FIFO live layers, summed in the service |
| `open_sales_orders` | `CountValueKpi` | `sales/queries.open_sales_orders` | count + Σ value of CONFIRMED / PARTIALLY_DELIVERED orders |
| `open_purchase_orders` | `CountValueKpi` | `procurement/queries.open_purchase_orders` | count + Σ value of APPROVED / SENT / PARTIALLY_RECEIVED POs |
| `otd_percent` | `OtdKpi` | `sales/queries.on_time_delivery` | simple delivery-vs-requested OTD (see below) |
| `wip_value` | `MoneyKpi` | `finance/queries.wip_balance` | the WIP-clearing account balance — the authoritative open-WIP figure (D-048) |

### Sanctioned cross-module query additions

These were added to the source modules' `queries` so reporting can read each KPI **downward** without
importing any service/model (STRUCTURE §5; finance never imports reporting → no cycle):

- `finance/queries/dashboards.py` — `cash_position`, `ar_aging_summary`, `ap_aging_summary`,
  `wip_balance` (+ the `AgingBuckets` dataclass). The aging summaries facade
  `service.{ar,ap}_aging.{customer,vendor}_aging` (the same pure projection the AR/AP **reports** use),
  collapsing the report's 61-90 + over-90 tail into one 90+ bucket.
- `sales/queries/dashboards.py` — `open_sales_orders` (tenant-wide count + value) and
  `on_time_delivery`.
- `procurement/queries.py` — `open_purchase_orders` (tenant-wide count + value).

Inventory needed **no new query**: the service sums the existing `valuation_summary` dict.

### OTD is a deliberately simple, best-effort metric (D-058)

`on_time_delivery` counts, of the tenant's **POSTED deliveries** joined to their sales order, how many
shipped on or before the order's single `requested_date` (`delivery_date <= requested_date`), out of
the total that **have** a requested_date. It is measured at the **delivery level** against the order's
single requested date — **not** a line-level promised-date model, **not** confirmed-vs-requested, no
partial-shipment weighting. Deliveries on an order with no requested_date are excluded from both
numerator and denominator. A rigorous per-line promised-date OTD is a documented later (parity §SD).

## Role-based gating (the dashboard returns only your role's KPIs)

The dashboard is **role-based** (D-058 / D-009): each KPI is gated by the **source module's read
permission** (`KPI_PERMISSIONS` in `constants.py`). The endpoint is guarded by the base
`reporting.dashboard.read` key (the price of admission); the service then computes a KPI **only** when
the caller holds its source key, and `response_model_exclude_none` drops the KPIs the caller may not
see. So the **response shape is the caller's role**:

| KPI | Gating permission |
|---|---|
| `cash_position`, `wip_value` | `finance.statements.read` |
| `ar_aging` | `finance.ar.read` |
| `ap_aging` | `finance.ap.read` |
| `inventory_value` | `inventory.valuation.read` |
| `open_sales_orders`, `otd_percent` | `sales.order.read` |
| `open_purchase_orders` | `procurement.po.read` |

A finance role sees cash / AR / AP / WIP; a sales role sees open sales orders + OTD; an inventory role
sees inventory value; a buyer sees open POs.

## The single-call dashboard (PERFORMANCE §4 / §6)

The **client makes one call** to `GET /api/v1/reporting/dashboard`, which internally runs a **fixed,
bounded** set of KPI aggregates — one (or, for inventory value, two) per **permitted** KPI, each O(1)
over its module's covering index. So PERFORMANCE §4's "one screen ≤ 3 calls" holds: the dashboard
screen is a single endpoint call. The internal aggregate count **exceeds 3 by design** (~12 statements
for the full 8-KPI bundle: auth user + functional currency + the per-KPI aggregates + the WIP
posting-default lookup) — it is **N aggregates for N KPIs, never N+1**; a test asserts the bundle stays
under a fixed ceiling (16), so a regression into per-row queries is caught.

**No ETag** (PERFORMANCE §3): KPI cards are **live** figures (a posted journal / shipped delivery
changes them immediately), so a conditional-GET would serve stale numbers. `as_of` (optional, defaults
today) bounds the date-bounded figures (cash / aging / WIP).

## Money as strings

Dashboard money fields serialize as **exact-decimal strings**, not JSON numbers (the `MoneyStr`
annotated type in `schemas.py`) — a KPI card is a display surface read by JS clients where a float
round-trip would corrupt the decimal. The value stays a `Decimal` in Python; only the wire form is a
string. `OtdKpi.percent` is a plain ratio (0-100, one decimal), not money.
