# CLAUDE.md — Permanent Project Memory for Atlas ERP

Atlas ERP is an open-source, industry-agnostic ERP platform. Its explicit functional benchmark is **SAP S/4HANA**. Everything in this file is binding for every working session.

## Session protocol (read this first, always)

1. **After any compaction or new session: read CLAUDE.md, PLAN.md, PROGRESS.md, and DECISIONS.md before writing any code.** Verify the last PROGRESS.md entry against the actual code and `git log`, then resume from the next unchecked PLAN.md task. Never guess at prior state.
2. **All file creation, naming, and placement MUST follow STRUCTURE.md. Re-read it after any compaction.** Before creating any new file, run `git status` and inspect the tree to re-anchor on actual structure.
3. **All git and GitHub operations MUST follow GITHUB-WORKFLOW.md. Re-read it after any compaction.** Branch model: `main` (production, promotion PRs only) ← `dev` (integration) ← short-lived feature branches. Issue-first for every discovered problem.
4. **All code MUST comply with PERFORMANCE.md. Re-read it after any compaction.** Every endpoint's Definition of Done includes the PERFORMANCE.md §6 checklist: FK + filter columns indexed, query-count assertion passes (≤3 per list request), paginated, money is Decimal, heavy work bulk/background, perf-suite coverage for hot paths. Target: 50 concurrent users on a 4 vCPU / 8 GB VPS within the §5 latency budgets.
5. Work in small units: implement one task → run its tests → commit → update PROGRESS.md → next task. **Definition of done: code written, tests passing, committed, logged in PROGRESS.md** — plus, for endpoints, the PERFORMANCE.md §6 checklist. A task that isn't committed and logged does not exist.
6. Append one line to PROGRESS.md after every completed task and tick the checkbox in PLAN.md. Record every consequential design decision in DECISIONS.md the moment it is made.
7. No pseudocode, no placeholders, no stubs, no TODO comments. Every file must be complete and working. When scope forces a trade-off, choose a smaller surface that fully works, and record the cut in `docs/research/s4hana-parity.md`.

## Tech stack (non-negotiable)

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (typed, async), PostgreSQL-first models (SQLite-compatible for the demo/test run), Alembic migrations, Pydantic v2. Dependency manager: **uv** (`uv.lock` committed).
- **Frontend:** React 18 + TypeScript + Vite, TanStack Query + TanStack Router, Tailwind. In-house component library only (data grid, form builder, kanban, dashboard cards, document-flow viewer). Fiori-inspired role-based home pages. Package manager: npm.
- **API:** REST, versioned `/api/v1`, OpenAPI docs, cursor pagination, consistent error envelope, idempotency keys on every endpoint that creates a financial or stock document.

## Architecture rules (hardcoded inheritances from S/4HANA)

1. **Universal Journal:** one append-only financial line-item table is the single source of truth. All FI and CO views (P&L, balance sheet, cost-center reports, margin analysis) are projections of it — never separately stored totals.
2. **Document flow:** every business document (PO, receipt, delivery, invoice, journal…) records its predecessor/successor links; the UI can render the full chain for any document.
3. **Multi-tenancy:** row-level `tenant_id` on every table, enforced by a session-level filter that query authors cannot bypass.
4. **Auth & RBAC:** JWT access+refresh, argon2 hashing; roles → permissions → resources as data (`finance.journal.post`); field-level read masking for HR compensation/IDs.
5. **Audit:** append-only audit table (actor, tenant, entity, before/after diff, timestamp, IP) written by middleware, not per-endpoint code.
6. **Event bus:** in-process domain-event dispatcher decouples modules (`SalesOrderShipped` → inventory issues stock → finance posts COGS); swappable for Kafka/Redis without touching business logic. Cross-module effects go through events; synchronous cross-module reads only via the owning module's `queries.py` (see STRUCTURE.md §5).
7. **Service layer owns business rules; routers thin; models logic-free.** Financial invariants live in code AND DB constraints (e.g. CHECK: exactly one of debit/credit > 0 per line).
8. Posted journal entries are immutable; corrections only via reversing entries. Postings to closed periods are rejected at service AND DB level.

## Coding conventions

Naming, file placement, size caps (400-line Python / 300-line TSX), import rules, and the terminology lock are defined in STRUCTURE.md §7–§8. Canonical terms: `item` (not product/sku), `vendor` (not supplier), `customer`, `warehouse`, `journal entry`. Industry templates may override display labels, never internal names.

## Build order (strict — from PLAN.md)

0. State files → 1. S/4HANA research + parity doc → 2. Full plan + key decisions → 3. `core/` (tenancy, auth, RBAC, audit, events, docflow, numbering, base models) → 4. Finance/Controlling → 5. Inventory → 6. Procurement → 7. Sales → 8. Manufacturing → 9. Quality/Maintenance → 10. HR → 11. Projects → 12. CRM → 13. Reporting → 14. Admin + onboarding → 15. Frontend design system, then module UIs in the same order → 16. Seed data → 17. README/diagrams/parity reconciliation.

Tests and commits accompany every step, never batched at the end. If scope must be cut: cut frontend polish before backend correctness, and module breadth before financial-engine depth — and record every cut in the parity doc.

## Environment notes (this machine)

- `uv` and `python3.12` live at `~/.local/bin/` (not on default PATH in fresh shells; invoke as `~/.local/bin/uv`).
- Backend commands run from `backend/`: `uv sync`, `uv run pytest -q`, `uv run ruff check .`
- Frontend commands run from `frontend/`: `npm ci`, `npm run typecheck`, `npm run build`.
- GitHub repo: `Taha-Mahmoodi/atlas-erp` (public). CI = `.github/workflows/ci.yml`, jobs `backend` + `frontend`; both are required status checks on `main` and `dev`.
