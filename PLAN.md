# PLAN.md — Atlas ERP Build Plan

Single source of truth for build order and task status. Tick a checkbox only when the task meets the definition of done (code + tests passing + committed + PROGRESS.md entry). The full module-by-module task breakdown (Phases 3–17) is written in Phase 2, after the research phase fixes the scope; until then those phases carry their scope summary only.

## Phase 0 — Repository bootstrap & state files

- [x] 0.1 Create public GitHub repo `atlas-erp`, clone, `.gitignore` as first commit on `main`
- [x] 0.2 Create `dev` branch; feature branches flow per GITHUB-WORKFLOW.md
- [x] 0.3 Create the 16 project labels
- [x] 0.4 State files: CLAUDE.md, PLAN.md, PROGRESS.md, DECISIONS.md; copy STRUCTURE.md + GITHUB-WORKFLOW.md to repo root
- [x] 0.5 Governance: LICENSE (Apache-2.0), NOTICE, README skeleton, CONTRIBUTING.md, SECURITY.md, .env.example
- [x] 0.6 CI workflow (`backend` + `frontend` jobs, green even before those dirs exist) + PR template + issue templates
- [ ] 0.7 Bootstrap PR merged to `dev`; branch protection on `main` + `dev` requiring both CI checks

## Phase 1 — S/4HANA research & parity map

- [ ] 1.1 Parallel web research across 12 S/4HANA functional areas (FI, CO, MM-PUR, MM-IM/EWM, SD, PP, QM/PM, HCM, PS, cross-cutting, Fiori/analytics, industry solutions)
- [ ] 1.2 `docs/research/s4hana-parity.md`: parity table (capability → full/partial/out-of-scope → owning Atlas module → reason + later path), committed via PR

## Phase 2 — Full plan & key decisions

- [ ] 2.1 Expand Phases 3–17 below into numbered tasks with checkboxes, informed by the parity doc
- [ ] 2.2 Record the ~15 key architecture decisions in DECISIONS.md
- [ ] 2.3 Target file tree confirmed against STRUCTURE.md

## Phase 3 — Core platform (`backend/app/core/`)

Scope: config, async db + tenancy filter, auth (JWT + argon2), RBAC as data, audit middleware, event bus, document flow, numbering sequences, base models/mixins, shared schemas (pagination + error envelope), exceptions, deps, Alembic baseline, test harness. Tasks detailed in Phase 2.

## Phase 4 — Finance & Controlling (deepest module)

Scope: universal journal + COA, fiscal periods, multi-currency FX, AP, AR, cost/profit centers + allocations, tax engine, statements as projections, bank reconciliation, asset accounting lite. Tasks detailed in Phase 2.

## Phase 5 — Inventory & Warehouse

Scope: items (lot/serial, multi-UoM), multi-warehouse/bin, stock moves as SSOT, moving-average + FIFO costing, COGS events, reorder points, counts. Tasks detailed in Phase 2.

## Phase 6 — Procurement

Scope: vendor master, requisition → RFQ → PO → GR → 3-way match → AP bill, approval threshold rules as data. Tasks detailed in Phase 2.

## Phase 7 — Sales & Distribution

Scope: customer master, condition pricing, quote → order → delivery → invoice with partials/backorders, ATP, credit block, RMA + credit notes. Tasks detailed in Phase 2.

## Phase 8 — Manufacturing

Scope: versioned multi-level BOMs, work centers, routings, production orders with WIP journals, MRP run, rough capacity check. Tasks detailed in Phase 2.

## Phase 9 — Quality & Maintenance

Scope: GR inspection lots with disposition, equipment register, corrective + preventive maintenance orders. Tasks detailed in Phase 2.

## Phase 10 — Human Resources

Scope: employees (masked compensation), org chart, leave accruals/approvals, time tracking with allocations, simple payroll journal (flagged non-compliant). Tasks detailed in Phase 2.

## Phase 11 — Projects

Scope: projects/WBS as costing objects, time + purchases to WBS, project cost report. Tasks detailed in Phase 2.

## Phase 12 — CRM

Scope: leads → opportunities kanban, activities, convert to customer + quote. Tasks detailed in Phase 2.

## Phase 13 — Reporting & analytics

Scope: role dashboards, generic report builder (entity + columns + filters + group-by → grid JSON + CSV). Tasks detailed in Phase 2.

## Phase 14 — Admin & onboarding

Scope: tenant onboarding wizard with industry templates, user/role UI, audit viewer, exchange rates, tax codes, number sequences. Includes the industry template loader (Phase 4 of the product spec). Tasks detailed in Phase 2.

## Phase 15 — Frontend

Scope: design system first (data grid, form builder, kanban, KPI cards, doc-flow viewer), then module UIs in backend build order, role-based home pages. Tasks detailed in Phase 2.

## Phase 16 — Seed data

Scope: one demo tenant per industry template, ~3 months of interlinked transactions so every report shows real data. Tasks detailed in Phase 2.

## Phase 17 — Final assembly

Scope: docker-compose up (db + backend + frontend), README quickstart + Mermaid architecture/ERD, "what v1 excludes" section, parity-doc reconciliation against what was actually built. Tasks detailed in Phase 2.

## Promotion milestones (dev → main)

- `v0.1.0` core complete (after Phase 3)
- `v0.2.0` finance complete (after Phase 4)
- `v0.3.0` all backend modules complete (after Phase 14)
- `v0.4.0` frontend complete (after Phase 15)
- `v1.0.0` final (after Phase 17)
