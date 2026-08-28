# Core platform (`backend/app/core/`)

The core package is the cross-cutting foundation every business module builds on. It owns no business concepts (no invoices, items, or employees); per [STRUCTURE.md](../../STRUCTURE.md) §2 those belong to modules. The full normative design of each mechanism is in [docs/architecture.md](../architecture.md) (decisions D-007…D-028); this guide is the operator/contributor map.

## What lives here

| File | Concern | Key decision |
|---|---|---|
| `config.py` | `ATLAS_`-prefixed settings (pydantic-settings) | — |
| `db.py` | async engine/session, `build_engine()` (attaches the SQLite FK pragma), guard installation | D-007 |
| `models.py` | declarative `Base`, mixins (`UuidPKMixin`, `TenantMixin`, `TimestampMixin`, `AuditMixin`), `tenant_fk()`, the core platform tables (users, refresh sessions, RBAC, audit log) | D-022 |
| `tenancy.py` | non-bypassable tenant filter + write stamping + `system_context()` | D-007 |
| `auth.py` | argon2id hashing, HS256 JWT primitives (no ORM) | D-008 |
| `security_router.py` | `/api/v1/auth` login / refresh / logout / me | D-008, D-027 |
| `rbac.py` | permission catalog, `resolve_permissions`, `require_permission`, `Masked()` | D-009 |
| `audit.py` | split-phase before/after diff capture, request context | D-010 |
| `db_guards.py` | per-dialect trigger DDL helpers for migrations (append-only, period close, immutability) | D-022 |
| `events.py` | in-process domain-event bus, `run_in_uow()` | D-011 |
| `docflow.py` + `docflow_router.py` | document registry, predecessor/successor links, chain traversal (`GET /api/v1/documents/{document_id}/chain`; the console calls it through `frontend/src/lib/docflow.ts`, which maps a chain onto `DocFlowViewer`) | D-012 |
| `numbering.py` | gapless per-tenant document sequences | D-012 |
| `idempotency.py` | reservation-based idempotency keys | D-013 |
| `pagination.py` | keyset (cursor) pagination | D-014 |
| `jobs.py` + `jobs_router.py` | background-job registry, in-process runner, `/api/v1/jobs` polling | D-032 |
| `schemas.py` / `exceptions.py` / `deps.py` | shared Pydantic bases + error envelope, exception hierarchy, FastAPI dependencies | D-014 |

## The guarantees a module inherits for free

1. **Tenant isolation.** Any model mixing in `TenantMixin` is automatically filtered to the active tenant on every ORM read/write; a query with no tenant context is a hard error unless inside `system_context()`. Composite `(tenant_id, id)` foreign keys are the schema-level backstop. Never write raw SQL against tenant tables in a module (`app/modules/` is grep-gated against `text(`).
2. **Auth & permissions.** Endpoints depend on `get_current_user` (sets the tenant + permission context) and gate with `require_permission("module.entity.action")`. Field-level masking is `Annotated[T | None, Masked(tp, "perm")]`.
3. **Audit.** Inserts/updates/deletes on `AuditMixin` models are captured automatically in the same transaction as the change. Never use ORM bulk `update()/delete()` on an audited model — it's a hard error; mutate loaded objects.
4. **Events.** Publish a `DomainEvent` with `publish(session, event)` and commit through `run_in_uow(session, work)`; subscribers in another module's `handlers.py` run in the same transaction, so cross-module effects are atomic with their trigger.
5. **Documents.** Register a business document with `register_document(...)`, link predecessors with `link_documents(...)`, and claim its number with `claim_number(...)` inside the committing transaction.
6. **Idempotency & pagination.** Guard document-creating endpoints with `Idempotent("endpoint")` + `idem.capture(...)`; return EVERY collection endpoint through `paginate(...)` + `map_page(...)` into the `Page` envelope — no bare-list responses (PERFORMANCE §3; #27). Responses ≥500 bytes are gzip-compressed app-wide (`GZipMiddleware` in `app/main.py`).
7. **Background jobs.** Long-running operations (PERFORMANCE §3: anything that can hit a proxy timeout — MRP, payment runs, statement imports >1k lines) never run in-request. Register a handler with `@register_job("module.operation")` (code-defined, like permissions), call `submit_job(session, ...)` inside the endpoint's `run_in_uow` work (the PENDING `core_jobs` row commits atomically with the idempotency capture, so a replayed key returns the same job id), then `schedule_job(job.id, factory)` strictly after the uow commit, and return `202 {job_id, status}`. Clients poll `GET /api/v1/jobs/{job_id}` (tenant-scoped; `GET /api/v1/jobs` lists with status/job_type filters). The runner re-establishes the submitting tenant context and audit actor and runs the handler inside `run_in_uow`, so events + audit behave exactly as in-request; failures roll the work back and surface as `FAILED` + error on the job row. Used today by `POST /finance/fx-revaluation-runs` and `POST /finance/payment-runs` (#26). Execution sits behind the `JobScheduler` Protocol (the event-bus seam pattern): the v1 in-process asyncio runner (capped at 4 concurrent) swaps for a real queue (arq/celery) by rebinding `jobs.scheduler`, with zero submitter changes. `core_jobs` is deliberately NOT audited (high-churn control rows, like refresh sessions).

## Database & migrations

- Migrations (`backend/alembic/versions/`) are the **only** schema source — `create_all` is never used, even in tests, because triggers live only in migrations.
- All schema runs on PostgreSQL (production) and SQLite (tests/demo). Per-dialect DDL (triggers) goes through `db_guards.py`. CI proves every migration applies, reverses, and re-applies on real Postgres and runs the `-m pg` guard subset there.
- Run locally: `make migrate` (SQLite by default), or set `ATLAS_DATABASE_URL` to a Postgres URL.

## Tests

`backend/tests/core/` mirrors the source. The suite uses the template-copy isolation pattern (D-025): one migrated SQLite template per session, copied per test, so real commits behave as in production. PostgreSQL-only behaviour is covered by `-m pg` tests. Run with `make test` (SQLite) and `make test-pg` (Postgres).

The perf smoke suite (`backend/tests/perf/`, `@pytest.mark.perf`, PERFORMANCE §5 / PLAN 4P.7) is excluded from the default run: it bulk-seeds ONE mid-volume tenant per session (~20k posted journal lines, ~1.5k customer invoices, Core executemany inserts per PERFORMANCE §2) onto its own database copy and asserts the median of 5 timed runs against the §5 wall-clock budgets — at 2× on the SQLite CI smoke (the non-blocking `perf-smoke` job, never a required status check) and at 1× against Postgres before each promotion. Run with `make perf` (SQLite) or `ATLAS_PERF_DATABASE_URL=postgresql+asyncpg://… make perf` (Postgres; each run seeds a fresh tenant). A budget failure before promotion is `severity:major`: fix or re-budget in DECISIONS.md — never delete the test.
