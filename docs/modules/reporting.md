# Reporting (`backend/app/modules/reporting/`)

Reporting is the **eleventh module** (Phase 13), sitting at the **top of the dependency order**
(STRUCTURE §5 / **D-058** / **D-059**). It has two areas: the **role-based dashboard** (PLAN 13.1 —
KPI cards: cash position, AR/AP aging, inventory value, open sales/purchase orders, OTD%, WIP) and
the **generic report builder** (PLAN 13.2 — an ad-hoc define-and-run query over a whitelist of
reportable entities → JSON grid + streaming CSV).

The normative design lives in [docs/architecture.md](../architecture.md) (D-021 statements/CO as
projections — reads existing data, never new stored totals; D-007 tenancy; D-009 RBAC + field
masking; D-014 error envelope; D-015 money types; D-048 WIP-clearing) and the **D-058** + **D-059**
decisions in [DECISIONS.md](../../DECISIONS.md); this guide is the operator/contributor map.

## Status

**Phase 13 / Reporting is COMPLETE** — 13.1 (dashboard) + 13.2 (report builder) both done.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `reporting.dashboard.read` + `reporting.report.run` base keys (registered at import) + the KPI catalog + `KPI_PERMISSIONS` map + the report-builder `FilterOperator` / `Aggregation` enums + the 10k `REPORT_ROW_CAP` | D-058, D-059, D-009 |
| `schemas.py` | dashboard KPI sub-models + `DashboardResponse`; the `ReportSpec` / `ReportResult` / entity-catalog schemas; money as strings | D-015, D-059 |
| `report_registry.py` | the report-builder **WHITELIST** — `ReportableEntity` / `ReportColumn` descriptors + the registered entities; **the ONE place reporting imports models** | D-059 |
| `report_builder.py` | `run_report` (JSON grid, 10k cap) + `stream_report_csv` (streaming export) — the ORM typed-bind construction | D-059, PERFORMANCE §3 |
| `service.py` | `dashboard_kpis(...)` — computes only the permitted KPIs off the source queries | D-058, D-021 |
| `router.py` | `GET /reporting/dashboard`; `GET /reporting/reports/entities`, `POST /reporting/reports/run`, `POST /reporting/reports/export` | D-009, D-059 |

**No `models.py`, no migration, no `queries.py`, no `events.py`/`handlers.py`.** Reporting owns **no
tables** (read-only over existing tables — the dashboard reads other modules' `queries`, the report
builder selects over their model classes), is a **leaf consumer** (nothing imports it, so a
`queries.py` would be an orphan — STRUCTURE §8.3), and triggers **no cross-module write**. The report
builder is **ad-hoc** (define-and-run, **no persisted report definitions** in v1). **No migration was
needed** — latest migration stays **0042**.

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
| `failed_jobs` | `FailedJobsKpi` | `core/jobs.Job` (no module `queries`) | count of jobs that ended FAILED in the last `FAILED_JOB_WINDOW_DAYS` (7). The ONE KPI whose source is **core** rather than a module: jobs are cross-cutting platform infrastructure owned by no business module, so there is nothing to read downward from. Gated on `admin.audit.read`, not a new key — same audience, strictly more powerful key, and a new key would leave existing Administrator roles unable to see the card. Drill-down is the existing `GET /api/v1/jobs?status=FAILED`. Added by **D-075** to pay D-072's FAILED-job-visibility clause |

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

# The report builder (PLAN 13.2, D-059)

The report builder is an **ad-hoc, define-and-run** generic query tool: a request names a
whitelisted entity + a subset of its columns + filters + group-by + aggregations, and gets back a
JSON grid (capped) or a streaming CSV. Nothing is persisted (no saved report definitions in v1).

## The whitelist-registry security model (the load-bearing idea)

The builder must **not** allow querying arbitrary tables/columns — that would be a SQL-injection /
data-exfiltration surface. So everything reportable is declared as **data** in
`report_registry.py`:

- A **`ReportableEntity`** names a stable `key` (e.g. `"finance.journal_lines"`), the ORM **model
  class** to query, the **source-module read permission** that gates it, and a dict of allowed
  columns.
- A **`ReportColumn`** carries the pre-resolved ORM attribute, a display label, a wire `type`
  (`str` / `number` / `date` / `bool`), and three capability flags: `filterable`, `groupable`,
  `is_aggregatable`.

A request can only reference a **registered** entity, a **subset** of its **registered** columns,
filters/group-by over columns flagged `filterable`/`groupable`, and aggregations over columns
flagged `is_aggregatable`. Anything else is a **400 `reporting.invalid_report`**. The builder never
reflects on the model beyond the registry; the column-name → ORM-attribute lookup goes through the
registry's allow-list (**never `getattr` on raw request input** against the model). The whitelist is
**closed**: a column not in an entity's dict does not exist for the builder.

### The registered entities (the initial safe set)

| Entity key | Model | Source permission |
|---|---|---|
| `finance.journal_lines` | `JournalLine` | `finance.journal.read` |
| `finance.accounts` | `Account` | `finance.account.read` |
| `inventory.items` | `Item` | `inventory.item.read` |
| `inventory.stock_moves` | `StockMove` | `inventory.move.read` |
| `sales.orders` | `SalesOrder` | `sales.order.read` |
| `procurement.purchase_orders` | `PurchaseOrder` | `procurement.po.read` |
| `hr.employees` | `Employee` | `hr.employee.read` |

## The masked-column exclusion (D-009 / D-052)

**Masked / sensitive columns are excluded from the whitelist outright** — they have no
`ReportColumn` entry, so they can never be selected, filtered, grouped, or aggregated through the
builder. The HR `Employee` entity exposes **only** non-sensitive columns (code, names,
department/position id, status, type, hire date); its compensation + PII — `base_salary`,
`currency_code`, `national_id`, `tax_id`, `date_of_birth`, `bank_account` — are **deliberately
absent**. Requesting one returns a 400 "unknown column". Masked data is not exposable through
reports, **by construction** (it is not in the registry at all), independent of the read-side `Masked`
serializer that guards the HR API.

## ORM typed-bind construction — no SQL injection (D-059)

The builder **never string-concatenates SQL**. It maps the spec's entity/column **names** to the
registry's pre-resolved ORM attributes, builds a SQLAlchemy `select()` over them, and applies filters
as **typed, bound** comparisons: the filter value is coerced to the column's Python type (the
`core/pagination` discipline) and **bound**, never interpolated. Operators come from a fixed set
(`EQ NE GT GTE LT LTE IN LIKE BETWEEN IS_NULL`); aggregations from a fixed set
(`COUNT SUM AVG MIN MAX`). A malicious-looking value such as `"'; DROP TABLE …"` is just a string
compared for equality — it matches nothing, executes nothing (pinned by an injection test on both
engines).

## Tenancy is auto-applied (D-007)

The select runs through the **tenant-filtered session**, so `core/tenancy.do_orm_execute` injects
the `tenant_id == current` predicate into every ORM statement — the builder writes no tenant WHERE
itself. Every whitelisted model is a `TenantMixin`, so the listener always fires; tenant A can never
see tenant B's rows (pinned by tenant-isolation tests at the service and API levels). **This is why
the builder must go through the ORM, not raw SQL** — only ORM statements get the auto-scope.

### The model-import exception (D-059, STRUCTURE §5)

`report_registry.py` is the **one** place reporting imports the model classes — a **read-only
query-construction** need (the builder selects/filters/groups over them through the tenant-filtered
session; it never calls their services and writes nothing). finance / inventory / sales / procurement
/ hr are all older and import nothing from reporting → one-directional, **no cycle**.

## The 10k cap + streaming CSV export (PERFORMANCE §3)

- `POST /reporting/reports/run` → `ReportResult` JSON. The builder fetches **`REPORT_ROW_CAP` (10k)
  + 1** rows; if the extra row arrives the result is truncated to 10k and `truncated=True` (the UI
  then offers the CSV export). A spec `limit` can only **lower** the cap, never raise it. ORDER BY a
  stable key (the entity's default order column + the PK) so results are deterministic.
- `POST /reporting/reports/export` → a **`StreamingResponse`** (`text/csv`, attachment). The CSV is
  generated **lazily** via `session.stream(...).partitions(...)` — never materialized in memory — so
  a result larger than the 10k JSON grid is served here. The spec is **validated eagerly** before the
  200 stream begins, so a malformed report fails as a normal 400 envelope rather than mid-body.
- `GET /reporting/reports/entities` → the whitelist catalog, **filtered to the entities the caller's
  role permits** (each gated by its source read permission), so a UI builds a role-correct picker.

## Role-based gating of the report builder (D-059 / D-009)

The endpoints are guarded by the base **`reporting.report.run`** key (the price of admission), then
each report is additionally gated by the named entity's **source-module read permission** (enforced
in-handler since the entity is in the request body): a 403 `rbac.permission_denied` if absent. So a
finance role can only report on finance entities, a sales role on sales, etc. — the report-builder
surface **is** the caller's role, exactly like the dashboard.
