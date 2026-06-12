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
- [ ] 3.6 Event bus: `core/events.py` in-process dispatcher (publish/subscribe, transactional semantics per DECISIONS), handler registration per module, tests
- [ ] 3.7 Document flow: `core/docflow.py` document registry + predecessor/successor links, chain traversal both directions, tests
- [ ] 3.8 Numbering + idempotency + pagination: per-tenant document sequences (INV-2026-00001) with portable locking, idempotency-key infrastructure for financial/stock-document endpoints, cursor pagination helpers, tests

**Promotion → `main` as v0.1.0 (core complete).**

## Phase 4 — Finance & Controlling (deepest module)

- [ ] 4.1 Chart of accounts (hierarchical, account types driving statements) + fiscal years/periods with open/closed states enforced at service AND DB level (per-dialect triggers)
- [ ] 4.2 Journal engine: entry header + line tables with dimension columns (cost center, profit center, project), exactly-one-of-debit/credit DB CHECK, debits==credits per currency enforced, posted-entry immutability (DB-level), reversal mechanics, posting service + router
- [ ] 4.3 Multi-currency: currencies + rates table, transaction/functional translation at posting, realized FX on settlement, unrealized FX revaluation run
- [ ] 4.4 Tax engine: configurable codes (rate, jurisdiction, inclusive/exclusive) applied at line level, tax account postings
- [ ] 4.5 Accounts Payable: vendor bills, payment runs, AP aging — all posting through the journal
- [ ] 4.6 Accounts Receivable: customer invoices, receipts, dunning levels, AR aging — all posting through the journal
- [ ] 4.7 Cost centers + profit centers masters, allocation rules, allocation run posting journals
- [ ] 4.8 Statements as pure projections: Trial Balance, P&L, Balance Sheet, Cash Flow (indirect), cost-center report, margin-by-product report
- [ ] 4.9 Bank reconciliation: bank accounts, CSV statement import, match suggestions, clearing postings
- [ ] 4.10 Asset accounting lite: asset register, straight-line + declining-balance depreciation runs posting journals

**Promotion → `main` as v0.2.0 (finance complete).**

## Phase 5 — Inventory & Warehouse

- [ ] 5.1 Items (stocked/non-stocked/service), item categories, multi-UoM with conversions, lot & serial masters
- [ ] 5.2 Warehouses + bins; stock moves as single source of truth; on-hand/availability projections
- [ ] 5.3 Costing: moving average AND FIFO (layer consumption) per item category; COGS auto-posted via events to finance
- [ ] 5.4 Physical/cycle counts with variance posting (stock move + journal)

## Phase 6 — Procurement

- [ ] 6.1 Vendor master: payment terms, currencies, approved items; vendor queries interface
- [ ] 6.2 Requisition → RFQ → PO flow with configurable approval threshold rules stored as data
- [ ] 6.3 Goods receipt: stock move + GR/IR journal via events, docflow links, optional inspection hook (flag only until Phase 9)
- [ ] 6.4 3-way match (PO/receipt/bill with tolerances) → AP bill; reorder points → auto-draft requisitions

## Phase 7 — Sales & Distribution

- [ ] 7.1 Customer master with credit limits; condition-style pricing (price lists per currency/customer group/date range, discounts)
- [ ] 7.2 Quote → Order with ATP check (on-hand + on-order) and credit-limit block at confirmation
- [ ] 7.3 Delivery with partial shipments + backorders → stock issue + COGS via events
- [ ] 7.4 Billing: invoice from delivery, revenue journals; RMA returns with credit notes

## Phase 8 — Manufacturing

- [ ] 8.1 Multi-level versioned BOMs, work centers, routings with setup/run times
- [ ] 8.2 Production orders: material reservation, issue to WIP, finish to stock, WIP journals feeding product costing
- [ ] 8.3 MRP run (explode sales demand + reorder points vs supply → planned orders) + rough capacity check (load vs available hours)

## Phase 9 — Quality & Maintenance

- [ ] 9.1 Quality: inspection flag on goods receipt → inspection lot → accept/reject with stock disposition
- [ ] 9.2 Maintenance: equipment register, corrective + preventive (interval-based) maintenance orders

## Phase 10 — Human Resources

- [ ] 10.1 Employees (masked compensation fields), departments, positions, org chart
- [ ] 10.2 Leave: types, accruals, approval flow
- [ ] 10.3 Time tracking with project & cost-center allocation
- [ ] 10.4 Simple gross→net payroll posting a journal, explicitly flagged as not jurisdiction-compliant

## Phase 11 — Projects

- [ ] 11.1 Projects with WBS elements as costing objects; time + purchases postable to WBS; project cost report

## Phase 12 — CRM

- [ ] 12.1 Leads → opportunities kanban, activities, convert to customer + quote

## Phase 13 — Reporting & analytics

- [ ] 13.1 Role-based dashboard KPI endpoints: cash position, AR/AP aging, inventory value, open orders, OTD%, WIP
- [ ] 13.2 Generic report builder: entity + columns + filters + group-by → JSON for the grid + CSV export

## Phase 14 — Admin, industry layer & onboarding

- [ ] 14.1 Industry template schema (`industry-templates/_schema.yaml`) + validating idempotent loader + the five templates (manufacturing, retail, professional-services, healthcare, construction) with terminology overrides, COA presets, tax codes, UoMs, module toggles, typed custom fields, approval presets, numbering formats
- [ ] 14.2 Tenant onboarding wizard: company info → industry template → COA/units/tax/workflows/numbering instantiated automatically
- [ ] 14.3 Admin endpoints: user/role management, audit viewer, exchange rates, tax codes, per-tenant number sequences

**Promotion → `main` as v0.3.0 (all backend modules complete).**

## Phase 15 — Frontend

- [ ] 15.1 Scaffold: Vite + React 18 + TS strict, Tailwind, TanStack Router/Query, `lib/apiClient.ts`, `lib/auth.ts`, `lib/queryClient.ts`, `lib/format.ts`, typecheck/build green in CI
- [ ] 15.2 Design system: DataGrid, FormBuilder, Kanban, KpiCard, DocFlowViewer (ERP-agnostic, tested)
- [ ] 15.3 App shell: login, role-based home pages with tiles + KPIs, navigation
- [ ] 15.4 Finance UIs (COA, journal entries + posting, AP/AR workbenches, statements, bank rec, assets)
- [ ] 15.5 Inventory UIs (items, stock overview, moves, counts)
- [ ] 15.6 Procurement UIs (vendors, requisitions, RFQs, POs, receipts, match)
- [ ] 15.7 Sales UIs (customers, pricing, quotes, orders, deliveries, invoices, returns)
- [ ] 15.8 Manufacturing UIs (BOMs, work centers, routings, production orders, MRP results)
- [ ] 15.9 Quality + Maintenance UIs (inspection lots, equipment, maintenance orders)
- [ ] 15.10 HR UIs (employees, org chart, leave, time, payroll run)
- [ ] 15.11 Projects + CRM UIs (WBS + cost report; leads/opportunities kanban)
- [ ] 15.12 Reporting + admin UIs (dashboards, report builder, onboarding wizard, user/role admin, audit viewer)

**Promotion → `main` as v0.4.0 (frontend complete).**

## Phase 16 — Seed data

- [ ] 16.1 `backend/seed.py`: one demo tenant per industry template with ~3 months of interlinked transactions (procure-to-pay, order-to-cash, make-to-stock, HR/time/payroll, projects) so every report shows real data

## Phase 17 — Final assembly

- [ ] 17.1 `docker-compose up` verified end-to-end (db + backend + frontend); README: <10-step quickstart, Mermaid architecture diagram, Mermaid ERD, "What v1 deliberately excludes and how to add it"
- [ ] 17.2 Reconcile `docs/research/s4hana-parity.md` against what was actually built; update any capability whose status changed
- [ ] 17.3 Final self-check loops (STRUCTURE.md §9 + GITHUB-WORKFLOW.md §9), close or document every open issue

**Promotion → `main` as v1.0.0.**

## Scope-cut rule

If scope must be cut: cut frontend polish before backend correctness, and module breadth before financial-engine depth. Every cut lands in the parity doc in the same PR that makes it.
