# PLAN.md — Atlas ERP Build Plan

Single source of truth for build order and task status. Tick a checkbox only when the task meets the definition of done (code + tests passing + committed + PROGRESS.md entry). **One task = one feature branch = one PR into `dev`** (GITHUB-WORKFLOW.md §2). Scope per task is fixed by the parity doc (`docs/research/s4hana-parity.md`); deviations must update that doc in the same PR.

## Phase 0 — Repository bootstrap & state files

- [x] 0.1 Create public GitHub repo `atlas-erp`, clone, `.gitignore` as first commit on `main`
- [x] 0.2 Create `dev` branch; feature branches flow per GITHUB-WORKFLOW.md
- [x] 0.3 Create the 16 project labels
- [x] 0.4 State files: CLAUDE.md, PLAN.md, PROGRESS.md, DECISIONS.md; copy STRUCTURE.md + GITHUB-WORKFLOW.md to repo root
- [x] 0.5 Governance: LICENSE (Apache-2.0), NOTICE, README skeleton, CONTRIBUTING.md, SECURITY.md, .env.example
- [x] 0.6 CI workflow (`backend` + `frontend` jobs, green even before those dirs exist) + PR template + issue templates
- [x] 0.7 Bootstrap PR merged to `dev`; branch protection on `main` + `dev` requiring both CI checks

## Phase 1 — S/4HANA research & parity map

- [x] 1.1 Parallel web research across 12 S/4HANA functional areas (FI, CO, MM-PUR, MM-IM/EWM, SD, PP, QM/PM, HCM, PS, cross-cutting, Fiori/analytics, industry solutions)
- [x] 1.2 `docs/research/s4hana-parity.md`: parity table (capability → full/partial/out-of-scope → owning Atlas module → reason + later path), committed via PR

## Phase 2 — Full plan & key decisions

- [x] 2.1 Expand Phases 3–17 into numbered tasks with checkboxes, informed by the parity doc
- [x] 2.2 Record the key architecture decisions (~15–20) in DECISIONS.md
- [x] 2.3 Target file tree confirmed against STRUCTURE.md (no new locations invented; D-011/D-015/D-016 amendments applied to STRUCTURE.md §2/§5)

## Phase 3 — Core platform (`backend/app/core/`)

- [x] 3.1 Backend scaffold: uv project (pyproject + uv.lock), ruff + pytest config, `app/main.py` factory, `core/config.py`, `core/db.py` (async engine/session), `core/models.py` (Base + TimestampMixin), `core/schemas.py` (error envelope, pagination bases), `core/exceptions.py`, health endpoint, Alembic init + baseline migration, test harness (`tests/conftest.py`), Makefile + docker-compose.yml (D-006)
- [x] 3.2 Tenancy: `core/tenancy.py` (tenant ContextVar, non-bypassable session filter, insert/update guards), `tenants` table + TenantMixin, tenant-isolation tests (tenant A reading tenant B fails)
- [x] 3.3 Auth: users table, argon2 hashing, JWT access+refresh with rotation/revocation, login/refresh/logout endpoints, `get_current_user` dependency, tests
- [x] 3.4 RBAC: roles → permissions → resources as data, permission-check dependency (`finance.journal.post` style), field-level read-masking helper, permission catalog seeding, RBAC-denial tests
- [x] 3.5 Audit: append-only audit table (actor, tenant, entity, before/after diff, timestamp, IP), capture via session events + request middleware, tests
- [x] 3.6 Event bus: `core/events.py` in-process dispatcher (publish/subscribe, transactional semantics per DECISIONS), handler registration per module, tests
- [x] 3.7 Document flow: `core/docflow.py` document registry + predecessor/successor links, chain traversal both directions, tests
- [x] 3.8 Numbering + idempotency + pagination: per-tenant document sequences (INV-2026-00001) with portable locking [DONE — `core/numbering.py`, D-012], idempotency-key infrastructure for financial/stock-document endpoints [DONE — `core/idempotency.py` + migration 0007, D-013/D-028], cursor pagination helpers [DONE — `core/pagination.py`, D-014/D-028], tests

**Promotion → `main` as v0.1.0 (core complete).**

## Phase 4 — Finance & Controlling (deepest module)

- [x] 4.1 Chart of accounts (hierarchical, account types driving statements) + fiscal years/periods with open/closed states enforced at service AND DB level (per-dialect triggers)
- [x] 4.2 Journal engine: entry header + line tables with dimension columns (cost center, profit center, project), exactly-one-of-debit/credit DB CHECK, debits==credits per currency enforced, posted-entry immutability (DB-level), reversal mechanics, posting service + router
- [x] 4.3 Multi-currency: currencies + rates table, transaction/functional translation at posting, realized FX on settlement (deferred to AP/AR clearing — accounts wired), unrealized FX revaluation run
- [x] 4.4 Tax engine: configurable codes (rate, jurisdiction, inclusive/exclusive) applied at line level, tax account postings
- [x] 4.5 Accounts Payable: vendor bills, payment runs, AP aging — all posting through the journal
- [x] 4.6 Accounts Receivable: customer invoices, receipts, dunning levels, AR aging — all posting through the journal
- [x] 4.7 Cost centers + profit centers masters, allocation rules, allocation run posting journals
- [x] 4.8 Statements as pure projections: Trial Balance, P&L, Balance Sheet, Cash Flow (indirect), cost-center report, margin-by-product report
- [x] 4.9 Bank reconciliation: bank accounts, CSV statement import (background job per PERFORMANCE §3 when >1k lines), match suggestions, clearing postings
- [x] 4.10 Asset accounting lite: asset register, straight-line + declining-balance depreciation runs posting journals (bulk/set-based writes per PERFORMANCE §2)

## Phase 4P — PERFORMANCE.md integration & retrofits (mid-build addendum)

- [x] 4P.1 Commit PERFORMANCE.md at repo root; bind it in CLAUDE.md; add these tasks; per-endpoint DoD now includes the §6 checklist
- [x] 4P.2 Retrofit: SQL query-count fixture (SQLAlchemy event listener) in tests/conftest.py; every existing list-endpoint test asserts query_count ≤ 3 (PERFORMANCE §2); fix any N+1 found (issue-first)
- [x] 4P.3 Retrofit: audit every FK + hot filter column across migrations 0002–0015 against PERFORMANCE §1; one migration adding all missing indexes (tenant_id leads composites); issue-first per finding
- [x] 4P.4 Retrofit: gzip response middleware (PERFORMANCE §3); assert pagination is mandatory on every collection endpoint (cursor, default 50, max 200) — closes #27
- [x] 4P.5 Background-job core (PERFORMANCE §3): in-process job runner + `core_jobs` table + job-id/polling endpoint pattern for long operations (bank-statement imports >1k lines, MRP, big payment runs); required before 4.9 import and Phase 8 MRP — closes #26 (FX revaluation + payment runs backgrounded, D-032)
- [x] 4P.6 ETag/If-None-Match on slow-changing reference data (COA, item master, settings) (PERFORMANCE §3) — closes #28 (collection-level weak ETag in core/conditional.py, D-035)
- [x] 4P.7 tests/perf/ suite (@pytest.mark.perf): journal list w/ filters, trial balance, P&L, AR aging — wall-clock budgets per PERFORMANCE §5 (SQLite CI smoke at 2× budget, non-blocking CI job; Postgres locally before each promotion)

**Promotion → `main` as v0.2.0 (finance complete) — requires 4P.2–4P.4 done and the 4P.7 perf smoke green.**

## Phase 5 — Inventory & Warehouse

- [x] 5.1 Items (stocked/non-stocked/service), item categories, multi-UoM with conversions, lot & serial masters
- [x] 5.2 Warehouses + bins; stock moves as single source of truth; on-hand/availability projections
- [x] 5.3 Costing: moving average AND FIFO (layer consumption) per item category; COGS auto-posted via events to finance
- [x] 5.4 Physical/cycle counts with variance posting (stock move + journal) — **Phase 5 / Inventory COMPLETE**

## Phase 6 — Procurement

- [x] 6.1 Vendor master: payment terms, currencies, approved items; vendor queries interface
- [x] 6.2 Requisition → RFQ → PO flow with configurable approval threshold rules stored as data
- [x] 6.3 Goods receipt: stock move + GR/IR journal via events, docflow links, optional inspection hook (flag only until Phase 9)
- [x] 6.4 3-way match (PO/receipt/bill with tolerances) → AP bill; reorder points → auto-draft requisitions — **Phase 6 / Procurement COMPLETE**

## Phase 7 — Sales & Distribution

- [x] 7.1 Customer master with credit limits; condition-style pricing (price lists per currency/customer group/date range, discounts)
- [x] 7.2 Quote → Order with ATP check (on-hand + on-order) and credit-limit block at confirmation
- [x] 7.3 Delivery with partial shipments + backorders → stock issue + COGS via events
- [x] 7.4 Billing: invoice from delivery, revenue journals; RMA returns with credit notes — **Phase 7 / Sales COMPLETE** (the order-to-cash loop closes: quote → order → delivery → billing → AR invoice; RMA returns reverse both COGS and revenue)

## Phase 8 — Manufacturing

- [x] 8.1 Multi-level versioned BOMs, work centers, routings with setup/run times
- [x] 8.2 Production orders: material reservation, issue to WIP, finish to stock, WIP journals feeding product costing
- [x] 8.3 MRP run (explode sales demand + reorder points vs supply → planned orders) + rough capacity check (load vs available hours) — **COMPLETES Phase 8 / Manufacturing**

## Phase 9 — Quality & Maintenance

- [x] 9.1 Quality: inspection flag on goods receipt → inspection lot → accept/reject with stock disposition
- [x] 9.2 Maintenance: equipment register, corrective + preventive (interval-based) maintenance orders

## Phase 10 — Human Resources

- [x] 10.1 Employees (masked compensation fields), departments, positions, org chart
- [x] 10.2 Leave: types, accruals, approval flow
- [x] 10.3 Time tracking with project & cost-center allocation
- [x] 10.4 Simple gross→net payroll posting a journal, explicitly flagged as not jurisdiction-compliant

## Phase 11 — Projects

- [x] 11.1 Projects with WBS elements as costing objects; time + purchases postable to WBS; project cost report

## Phase 12 — CRM

- [x] 12.1 Leads → opportunities kanban, activities, convert to customer + quote (Phase 12 / CRM COMPLETE)

## Phase 13 — Reporting & analytics

- [x] 13.1 Role-based dashboard KPI endpoints: cash position, AR/AP aging, inventory value, open orders, OTD%, WIP
- [x] 13.2 Generic report builder: entity + columns + filters + group-by → JSON for the grid + CSV export

## Phase 14 — Admin, industry layer & onboarding

- [x] 14.1 Industry template schema (`industry-templates/_schema.yaml`) + validating idempotent loader + the five templates (manufacturing, retail, professional-services, healthcare, construction) with terminology overrides, COA presets, tax codes, UoMs, module toggles, typed custom fields, approval presets, numbering formats
- [x] 14.2 Tenant onboarding wizard: company info → industry template → COA/units/tax/workflows/numbering instantiated automatically
- [x] 14.3 Admin endpoints: user/role management, audit viewer, exchange rates, tax codes, per-tenant number sequences

**Promotion → `main` as v0.3.0 (all backend modules complete).**

## Phase 15 — Frontend

- [x] 15.1 Scaffold: Vite + React 18 + TS strict, Tailwind, TanStack Router/Query, `lib/apiClient.ts`, `lib/auth.ts`, `lib/queryClient.ts`, `lib/format.ts`, typecheck/build green in CI
- [x] 15.2 Design system: DataGrid, FormBuilder, Kanban, KpiCard, DocFlowViewer (ERP-agnostic, tested)
- [x] 15.3 App shell: login, role-based home pages with tiles + KPIs, navigation
- [x] 15.4 Finance UIs (COA, journal entries + posting, AP/AR workbenches, statements, bank rec, assets)
- [x] 15.5 Inventory UIs (items, stock overview, moves, counts)
- [x] 15.6 Procurement UIs (vendors, requisitions, RFQs, POs, receipts, match)
- [x] 15.7 Sales UIs (customers, pricing, quotes, orders, deliveries, invoices, returns)
- [x] 15.8 Manufacturing UIs (BOMs, work centers, routings, production orders, MRP results)
- [x] 15.9 Quality + Maintenance UIs (inspection lots, equipment, maintenance orders)
- [x] 15.10 HR UIs (employees, org chart, leave, time, payroll run)
- [x] 15.11 Projects + CRM UIs (WBS + cost report; leads/opportunities kanban)
- [x] 15.12 Reporting + admin UIs (dashboards, report builder, onboarding wizard, user/role admin, audit viewer)

**Promotion → `main` as v0.4.0 (frontend complete).**

## Phase 16 — Seed data

- [x] 16.1 `backend/seed.py`: one demo tenant per industry template with ~3 months of interlinked transactions (procure-to-pay, order-to-cash, make-to-stock, HR/time/payroll, projects) so every report shows real data
- [x] 16.2 `seed.py --volume` high-volume tenant (PERFORMANCE §5): ≥100k journal lines, ≥50k stock moves, ≥10k orders, ≥5k items, 3 fiscal years — bulk inserts, finishes in minutes; drives the tests/perf/ budgets

## Phase 17 — Final assembly

- [x] 17.1 `docker-compose up` verified end-to-end (db + backend + frontend); README: <10-step quickstart, Mermaid architecture diagram, Mermaid ERD, "What v1 deliberately excludes and how to add it"
- [x] 17.1b `docs/deployment.md` (PERFORMANCE §7): single-VPS topology + docker-compose.prod.yml with resource limits/tuned Postgres, sizing table, backup/restore drill, "why it stays fast"; full perf suite green on Postgres volume tenant before v1
- [x] 17.2 Reconcile `docs/research/s4hana-parity.md` against what was actually built; update any capability whose status changed
- [x] 17.3 Final self-check loops (STRUCTURE.md §9 + GITHUB-WORKFLOW.md §9), close or document every open issue

**Promotion → `main` as v1.0.0.**

## Phase 17b — Console design system

- [x] 17b.1 Art-direction pass for the authenticated console (the "porcelain" direction): measured extraction of the shipped UI, `DIRECTION.md`, DTCG `tokens.json` in both themes, coded specs for 7 surfaces × light/dark, 5 measured technique prototypes
- [x] 17b.2 Implement it: token remap reaching ~3,900 usages across 250 pages, light/dark as equals with a pre-paint boot script, rebuilt shell (248px sidebar, ⌘K glass command palette), shared primitives (Icon sprite, StatusPill, Sparkline, ErrorState, RouteErrorBoundary); fixes #180 (4xx → route error boundary), #181 (responsive shell), #182 (one canonical status vocabulary)
- [x] 17b.3 Module page bodies conformed: real breadcrumbs, detail summary panels, `isFiltered`/`onClearFilters` wired on every filterable list

**Promotion → `main` as v1.1.0.**

## Phase 18 — Machine credential (hospitality prerequisite, independently useful)

Plan: [`docs/research/hospitality-build-plan.md`](docs/research/hospitality-build-plan.md). Spec: that doc's Q1. Closes the "Released APIs and event-based integration" v1 scope cut recorded in `docs/research/s4hana-parity.md`.

- [x] 18.1 `ApiKey` model + migration; `mint_api_key`/`parse_api_key` on the tenant UUID; the API-key branch in `get_current_user` (one joined query, scopes intersect and may only narrow — D-069)
- [x] 18.2 Admin endpoints (create/list/revoke) behind `admin.apikey.manage`; a key may not mint a key wider than itself (D-070); credential lifecycle audited with `secret_sha256` excluded
- [x] 18.3 Per-credential rate limiting at the nginx edge; operator flow in `docs/api.md`

## Phase 19 — Restaurant Ordering

Spec: hospitality plan Q2 (stored availability, derived suggestion), Q4 (depletion), Q6 (website read path).

- [x] 19.1 `hospitality.yaml` industry template (6th): Guest/Group Account terminology, Guest Ledger + F&B Revenue COA split, FIFO costing default, BOM sub-engine only
- [x] 19.2 `hsp_menu_availability` — stored state (AVAILABLE/LIMITED/EIGHTY_SIXED), countdown auto-86, lazy expiry on read; the derived "at risk" staff list from on-hand only, batch-exploded, never guest-facing
- [x] 19.3 `order_ticket` document type: OPEN → SENT_TO_KITCHEN → IN_PREP → READY → SERVED → SETTLED, seat-level lines, KDS as a status-filtered query
- [x] 19.4 Per-sale ingredient depletion through the job runner — aggregated, chunked and backgrounded at fire (**D-072**, restaurant-module-scoped). Settlement flips the ticket to SETTLED and publishes `RestaurantOrderSettled`; **the invoice/payment settlement and split checks are deferred to Phase 20** with the folio that owns the money (cut recorded in `docs/modules/hospitality.md` §6)
- [x] 19.5 The website-facing read/write API: menu + availability reads with conditional GET, order writes under D-013 idempotency

## Phase 20 — Rooms & Folio

Spec: hospitality plan Q3 (overbooking), Q5 (folio, deposits, business date, night audit). Plan: [`docs/research/phase-20-rooms-folio-plan.md`](docs/research/phase-20-rooms-folio-plan.md). **20.4 changes shipped finance — this phase lands in `dev` and is reviewed by the owner before any promotion to `main`.**

- [ ] 20.1 `room_type`, `room` with housekeeping status, `rate_plan` (manual nightly rates); `housekeeping_task` document
- [ ] 20.2 `reservation` document type + the overbooking guard (counter tables, `with_for_update`, portable CHECK — no Postgres-only exclusion constraint, D-003)
- [ ] 20.3 `folio` document type: heterogeneous charge lines, doc-flow linked to their source documents, settlement posting
- [ ] 20.4 Advance deposits — widening finance's `CustomerReceipt` clearing engine rather than duplicating it (a change to shipped finance)
- [ ] 20.5 Business date + night audit as an idempotent job on the existing runner; group bookings with a master folio splitting back at settlement
- [ ] 20.6 The room-charge bridge: `order_ticket.settle(charge_to_room)` → `RestaurantOrderSettled` → a folio line with a doc-flow link back

## Phase 21 — Table Reservations

Spec: hospitality plan Q3 (the pacing counter) + "The guest-facing surface". Plan: [`docs/research/phase-21-table-reservations-plan.md`](docs/research/phase-21-table-reservations-plan.md). Owner-directed 2026-08-15. Independent of Phase 20 — no finance touch — and sequenced before it.

- [x] 21.1 `hsp_reservation_settings` + `hsp_service_slot` pacing counter: unique on `(tenant_id, service_date, slot_start)` on a fixed 15-minute grid, covers/parties CHECK pairs, upsert-on-lock from tenant defaults, manager slot overrides
- [x] 21.2 `table_reservation` document: CONFIRMED → SEATED → COMPLETED/NO_SHOW/CANCELLED, counter discipline per transition (release only before `slot_start`), seating opens a doc-flow-linked order ticket
- [x] 21.3 Website surface: slot-grid availability read with conditional GET, booking write under D-013 returning nearest alternatives on refusal, guest cancel; its own `hospitality.reservation.book` scope (D-069 narrowing)
- [x] 21.4 Staff book: list by service date, phone bookings through the same gate, seat/no-show/cancel endpoints

## Phase 22 — Platform hardening and the hospitality UI

The remaining-work priorities from [`docs/research/remaining-work-plan.md`](docs/research/remaining-work-plan.md), promoted here so they are tracked like any other task.

- [x] 22.1 **P0 — job-runner reliability**: handler idempotency, the stale-PENDING/RUNNING sweeper with an attempt ceiling, FAILED-job visibility, idempotency-key retention. Plan: [`docs/research/p0-job-runner-reliability-plan.md`](docs/research/p0-job-runner-reliability-plan.md). Pays back D-072's "bought back with alerting" clause
- [x] 22.2 **P1 — the hospitality module UI**: menu/86 management, the at-risk list, tickets, and the KDS board on the porcelain register. Plan: [`docs/research/p1-hospitality-ui-plan.md`](docs/research/p1-hospitality-ui-plan.md)
- [ ] 22.3 **P2 — the tracked minor issues** — #163, #164, #165 and #166 are SHIPPED to `dev` (PRs #194/#193/#197/#198, 2026-08-15); **#176 remains** and is the only reason this stays unticked. It was held out of the wave-1 fan-out deliberately: it rewrites `frontend/src/router.tsx`, which the hospitality-UI lane owned at the time. That lane has landed, so #176 is now unblocked. Plans: [`docs/research/p2-minor-issues-plan.md`](docs/research/p2-minor-issues-plan.md)

## Scope-cut rule

If scope must be cut: cut frontend polish before backend correctness, and module breadth before financial-engine depth. Every cut lands in the parity doc in the same PR that makes it.
