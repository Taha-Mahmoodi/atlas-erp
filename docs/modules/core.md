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
| `docflow.py` + `docflow_router.py` | document registry, predecessor/successor links, chain traversal | D-012 |
| `numbering.py` | gapless per-tenant document sequences | D-012 |
| `idempotency.py` | reservation-based idempotency keys | D-013 |
| `pagination.py` | keyset (cursor) pagination | D-014 |
| `schemas.py` / `exceptions.py` / `deps.py` | shared Pydantic bases + error envelope, exception hierarchy, FastAPI dependencies | D-014 |

## The guarantees a module inherits for free

1. **Tenant isolation.** Any model mixing in `TenantMixin` is automatically filtered to the active tenant on every ORM read/write; a query with no tenant context is a hard error unless inside `system_context()`. Composite `(tenant_id, id)` foreign keys are the schema-level backstop. Never write raw SQL against tenant tables in a module (`app/modules/` is grep-gated against `text(`).
2. **Auth & permissions.** Endpoints depend on `get_current_user` (sets the tenant + permission context) and gate with `require_permission("module.entity.action")`. Field-level masking is `Annotated[T | None, Masked(tp, "perm")]`.
3. **Audit.** Inserts/updates/deletes on `AuditMixin` models are captured automatically in the same transaction as the change. Never use ORM bulk `update()/delete()` on an audited model — it's a hard error; mutate loaded objects.
4. **Events.** Publish a `DomainEvent` with `publish(session, event)` and commit through `run_in_uow(session, work)`; subscribers in another module's `handlers.py` run in the same transaction, so cross-module effects are atomic with their trigger.
5. **Documents.** Register a business document with `register_document(...)`, link predecessors with `link_documents(...)`, and claim its number with `claim_number(...)` inside the committing transaction.
6. **Idempotency & pagination.** Guard document-creating endpoints with `Idempotent("endpoint")` + `idem.capture(...)`; return list endpoints through `paginate(...)`.

## Database & migrations

- Migrations (`backend/alembic/versions/`) are the **only** schema source — `create_all` is never used, even in tests, because triggers live only in migrations.
- All schema runs on PostgreSQL (production) and SQLite (tests/demo). Per-dialect DDL (triggers) goes through `db_guards.py`. CI proves every migration applies, reverses, and re-applies on real Postgres and runs the `-m pg` guard subset there.
- Run locally: `make migrate` (SQLite by default), or set `ATLAS_DATABASE_URL` to a Postgres URL.

## Tests

`backend/tests/core/` mirrors the source. The suite uses the template-copy isolation pattern (D-025): one migrated SQLite template per session, copied per test, so real commits behave as in production. PostgreSQL-only behaviour is covered by `-m pg` tests. Run with `make test` (SQLite) and `make test-pg` (Postgres).
