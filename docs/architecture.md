# Atlas ERP — Architecture

This document is the implementation contract derived from the Phase-2 architecture review. Each section below is a numbered decision (D-007 … D-026), also indexed in [DECISIONS.md](../DECISIONS.md). Implementers must follow these mechanisms exactly — table names, API names, constraint semantics, trigger behavior, and parameter values are normative, not illustrative. Any change requires a superseding DECISIONS.md entry referencing the decision it replaces.

---

## D-007 — Tenancy enforcement (non-bypassable session filter)

**Decision.**
Three cooperating layers live in `core/tenancy.py` + `core/db.py`:

1. **Context.** A `ContextVar[uuid.UUID | None]` named `current_tenant_id`, set only by `get_current_user` in `core/deps.py` after JWT validation (and by the refresh endpoint directly from the validated refresh-token `tenant_id` claim — refresh does NOT use `system_context`), reset via token in a `finally` block by a pure-ASGI middleware.
2. **Read/write filtering.** A global `@event.listens_for(Session, "do_orm_execute")` hook on the sync `Session` class (`AsyncSession` proxies it, so it covers all execute calls and relationship/lazy loads) adds `with_loader_criteria(TenantMixin, lambda cls: cls.tenant_id == current_tenant_id.get(), include_aliases=True, track_closure_variables=False)` to every ORM statement, including ORM-enabled `update()`/`delete()`. **Fail-closed:** if the statement touches any `TenantMixin` mapper and `current_tenant_id` is unset, raise `TenancyError` — unless the `system_context()` ContextVar (also in `core/tenancy.py`) is active. `system_context` is invoked in exactly four greppable places: login user-lookup, tenant provisioning in admin, Alembic/seed provisioning phase, and bus system-event replay.
3. **Write stamping.** A `before_flush` listener stamps `tenant_id` on new `TenantMixin` objects when unset and raises `TenancyError` when a new/dirty object's `tenant_id` differs from the context.
4. **DB backstop.** Every FK between tenant-scoped tables is composite `(tenant_id, <entity>_id)` referencing `UNIQUE (tenant_id, id)` on the parent, declared via a `tenant_fk()` helper in `core/models.py`. **Critical SQLite fix:** SQLite only enforces FKs with `PRAGMA foreign_keys=ON`, so `core/db.py` registers an engine `connect` event that emits the pragma on every SQLite connection (runtime, tests, seed) — without this the backstop silently does nothing on the test engine.

Core-level statements (Core `Table` inserts, `text()`) bypass the ORM hook; they are sanctioned only inside `core/` (audit writer, numbering, idempotency) where `tenant_id` is always explicit, enforced by a CI grep gate banning `text(` and Core `.insert(` under `app/modules/` (`tests/` is exempt — DB-guard tests need raw SQL).

Non-bypassability tests in `tests/core/test_tenancy.py` iterate `Base.registry.mappers` so new models are auto-covered. For every `TenantMixin` mapper assert: (a) bare `select()` under tenant A returns zero tenant-B rows; (b) relationship loads never leak; (c) ORM `update()` with no WHERE touches only tenant-A rows; (d) execution with unset ContextVar raises; (e) inserting a foreign `tenant_id` raises; (f) `session.get(cls, b_id)` under tenant A returns `None`.

**Rationale.**
`do_orm_execute` + `with_loader_criteria` is the only SQLAlchemy 2.0 mechanism that injects criteria into every ORM statement — including lazy loads and bulk ORM writes — with zero cooperation from query authors, which is the literal "cannot bypass" requirement. ContextVar is async-task-safe under FastAPI. Fail-closed converts "forgot to set tenant" from a leak into a hard error. Composite FKs give a schema-level invariant on both engines, but only if the SQLite FK pragma is actually on — the original draft omitted that, which would have made the backstop a no-op exactly where CI runs. Mapper-enumerating tests make the guarantee self-extending.

**Rejected alternatives.**
- PostgreSQL RLS with `SET LOCAL app.tenant_id`: unprovable in the SQLite CI/demo run, so it cannot be the primary mechanism; noted in DECISIONS.md as Postgres-only hardening post-v1.
- Per-query `.where()` helpers or custom Query base: bypassable by anyone writing `select()` directly.
- Schema- or database-per-tenant: contradicts the mandated row-level design and makes provisioning/Alembic disproportionately heavy.
- Mapper write-events only: guards writes, not reads.

**Risks & mitigations.**
- Raw SQL and Core statements bypass the hook — bounded by the grep gate, the composite-FK backstop, and review; residual gap recorded in DECISIONS.md.
- Identity-map hits (`session.get`) skip SQL — benign because the request-scoped session only ever holds same-tenant rows; sessions are never shared across requests.
- `track_closure_variables=False` is mandatory so the lambda re-reads the ContextVar per execution instead of baking in the first value seen; a dedicated test executes the same statement under two tenants in one process to pin this.

---

## D-008 — Auth token flow (JWT access+refresh, rotation with grace window, argon2)

**Decision.**
PyJWT, HS256, single `ATLAS_JWT_SECRET` (env, >=64 random bytes).

- **Access token:** 15-min TTL (`ATLAS_JWT_ACCESS_TTL_SECONDS`), claims `{sub: user_id, tenant_id, sid: refresh-session id, ver: user.token_version, typ: 'access', jti, iat, exp}`. Stateless, but `ver` is compared against `core_users.token_version` (the user row is loaded anyway for RBAC), so "revoke everything" = increment `token_version`. No permissions in the token.
- **Refresh token:** JWT, 14-day TTL (`ATLAS_JWT_REFRESH_TTL_SECONDS`), claims `{sub, tenant_id, sid, typ: 'refresh', jti, exp}`, delivered as an httpOnly Secure SameSite=Strict cookie scoped to path `/api/v1/auth`; the access token is returned in the JSON body and held in SPA memory only.
- **Server state:** `core_refresh_sessions` (id uuid = sid, tenant_id, user_id, current_jti_hash sha256, prev_jti_hash sha256 nullable, rotated_at, issued_at, last_used_at, expires_at, revoked_at nullable, ip, user_agent).
- **Rotation with reuse detection AND a 10-second grace window** (promoted from "later" to v1 because the SPA's multi-tab reality makes benign races routine; see D-024). `POST /api/v1/auth/refresh` verifies signature+typ, sets the tenancy ContextVar from the token's `tenant_id` claim, loads the session row by `sid`; then:
  - presented-jti hash == `current_jti_hash` → rotate via single `UPDATE ... SET prev_jti_hash=current_jti_hash, current_jti_hash=:new, rotated_at=now() WHERE id=:sid AND current_jti_hash=:old` (compare-and-swap; the loser of a true race gets 0 rows, then re-reads and falls into the grace branch);
  - presented-jti == `prev_jti_hash` AND `now() - rotated_at < 10s` → benign concurrent refresh: rotate again normally from the current chain;
  - any other mismatch → replay: set `revoked_at` on the whole session family, 401.
- **Logout** revokes the sid row and clears the cookie.
- **Login** (`POST /api/v1/auth/login`, body `tenant_slug+email+password`) runs under `system_context()` for tenant+user resolution.
- **Passwords:** argon2-cffi `PasswordHasher(type=argon2id, time_cost=3, memory_cost=65536, parallelism=4)` per RFC 9106, executed via `anyio.to_thread.run_sync`; `check_needs_rehash()` upgrades on successful login.
- **`core/deps.py`:** HTTPBearer scheme → `get_current_user` decodes, validates typ/exp/ver, sets the tenancy ContextVar, returns a frozen `CurrentUser` dataclass (user_id, tenant_id, permissions frozenset).

**Rationale.**
HS256 is sufficient for a single-process monolith — no key-distribution problem exists. Short stateless access tokens keep validation DB-free while `ver` gives an instant global-revoke valve. Hashing the stored jti means a DB leak cannot mint sessions; CAS rotation gives airtight replay detection; the prev_jti grace window is the standard refinement that distinguishes a two-tab race or a lost response from actual token theft — without it, ordinary SPA usage triggers family revocation and forced logouts. Cookie-held refresh + memory-held access is the standard XSS/CSRF compromise. Argon2 at 64 MiB takes tens of ms, so thread offload is mandatory.

**Rejected alternatives.**
- RS256/EdDSA: key-management cost for a consumer that doesn't exist; revisit only if a second service validates tokens.
- Opaque DB refresh tokens: the constraint specifies JWT access+refresh; JWT also rejects garbage pre-DB.
- Redis denylist for access revocation: forbidden infrastructure; 15-min exposure + `ver` bump suffices.
- localStorage refresh tokens: XSS-exfiltratable.
- bcrypt: overridden by the argon2 constraint.
- No-grace strict rotation (original draft): converts routine multi-tab refresh races into family revocations.

**Risks & mitigations.**
- Symmetric key compromise forges any token — env-only storage, never log tokens, short access TTL.
- The 10 s grace window slightly widens the replay-detection blind spot — accepted: an attacker inside 10 s of a legitimate rotation still cannot extend the chain invisibly because every rotation updates prev/current atomically and the family dies on the next out-of-chain presentation.
- SameSite=Strict assumes SPA and API share a site; a split-origin deploy must move to SameSite=None + CSRF token (documented in DECISIONS.md).

---

## D-009 — RBAC data model, permission dependency, field masking

**Decision.**
Four tables:

- `core_permissions` (id, key UNIQUE like `'finance.journal.post'`, description) — a global code-defined catalog: each module declares keys as constants in its `constants.py`, a registry in `core/rbac.py` collects them, and startup sync + `seed.py` upsert the catalog; permissions are not tenant-editable.
- `core_roles` (id, tenant_id, name, description, is_system; UNIQUE(tenant_id, name)) — tenant-scoped, system roles seeded from industry templates at provisioning.
- `core_role_permissions` (role_id, permission_id, composite PK).
- `core_user_roles` (tenant_id, user_id, role_id, composite PK).

**Check path:** `require_permission(key)` factory in `core/rbac.py` returns an async dependency depending on `get_current_user`; effective permissions resolved once per request by one join query (user_roles ⋈ role_permissions ⋈ permissions), memoized in an in-process TTL cache (60 s) keyed `(tenant_id, user_id, token_version)`; missing key → 403 with envelope code `'permission_denied'` naming the key. Routers attach per route: `dependencies=[Depends(require_permission(FIN_JOURNAL_POST))]`. The resolved frozenset lands on `CurrentUser` and in a `current_permissions` ContextVar set by `get_current_user`.

**Field-level read masking** (HR compensation/IDs): a `Masked(tp, permission)` factory in `core/schemas.py` returning `Annotated[tp | None, WrapSerializer(functools.partial(_mask_serializer, permission))]` — the permission is bound via `functools.partial` closure (NOT loose Annotated metadata, which a WrapSerializer cannot read); the serializer reads `current_permissions` at serialization time and returns the real value only if the key (e.g. `'hr.employee.read_compensation'`) is present, else `None`. Works under `response_model` serialization without plumbing `SerializationInfo.context`.

**Write side:** masked fields are excluded from the entity's Update schema and live behind a separate endpoint+schema guarded by the corresponding update permission, so a partial update can never silently null compensation.

**Rationale.**
Tenant-scoped roles over a code-owned catalog satisfies "RBAC as data" while preventing tenants from inventing keys no code checks. One resolution query + short TTL cache makes per-route checks O(1) without baking stale permissions into JWTs (revocation lands within 60 s, or instantly via `token_version` bump which changes the cache key). The partial-bound WrapSerializer is idiomatic Pydantic v2, declares the guarding permission on the field itself, and centralizes masking in one core construct. Masking to `None` keeps response types honest for the TypeScript mirror (`field: string | null`).

**Rejected alternatives.**
- Permissions embedded in JWT: stale for 15 min and bloats the token; the user row is loaded anyway.
- Per-tenant permission catalogs: orphan keys nothing enforces.
- Casbin/oso engines: external DSLs fight "RBAC as data + service layer owns logic" and complicate the dual-engine story.
- Per-schema `computed_field` masking: scatters security logic across modules.
- `response_model_exclude` per route: route-level, not principal-level, and drifts silently.

**Risks & mitigations.**
- ContextVar-dependent serialization masks everything outside a request (tests, jobs) — fail-closed and correct; the test harness provides a `permissions_context` fixture that sets the ContextVar explicitly.
- TTL cache lags grants up to 60 s per process (multi-worker deploys lag per worker) — documented; admin "revoke now" bumps `token_version`.
- Masked-`None` is ambiguous with genuinely-null values for authorized readers — accepted for v1; add a sibling `is_masked` boolean in the same serializer if it bites.

---

## D-010 — Audit capture (split-phase session-event diffs + middleware context)

**Decision.**
Two layers with disjoint responsibilities in `core/audit.py`.

**Data layer**, split across three Session events to be correct about both attribute history and generated PKs:

1. `before_flush` walks `session.dirty` and `session.deleted` for `AuditMixin` models and computes per-column diffs from `inspect(obj).attrs[col].history` (`{field: {old, new}}` for changed columns; old values for deletes) — history is only guaranteed pre-flush, so updates/deletes are captured here, not in `after_flush` as the original draft had it.
2. `after_flush` walks `session.new` and captures insert rows from current column values — final generated PKs exist here.
3. `after_flush_postexec` writes all buffered rows (buffer lives in `session.info`, drained per flush — multi-flush transactions produce multiple batches) via ONE Core `session.execute(insert(core_audit_log), rows)` on the same connection — same transaction, so audit is exactly as atomic as the change, and event-handler writes are captured automatically because flush events fire for the shared session.

Columns are skipped per-model via `__audit_exclude__` (`password_hash` always; HR compensation is captured but the audit viewer masks it with the same `Masked` machinery).

**Context layer:** a pure-ASGI middleware creates `RequestContext` (request_id uuid, ip with trusted-proxy X-Forwarded-For handling, user_agent, method+path) in a ContextVar; `get_current_user` fills actor_user_id/tenant_id; the flush listeners read it (absent → actor NULL, source='system').

**Table `core_audit_log`:** id bigint identity, tenant_id NULLABLE, actor_user_id nullable, source (`'http'`|`'system'`), action (`'insert'`|`'update'`|`'delete'`), entity_table, entity_id text, diff JSON (JSONB via `with_variant`), request_id, ip, created_at; index (tenant_id, entity_table, entity_id, created_at). It does NOT carry `TenantMixin` (fix: `TenantMixin` implies NOT NULL + fail-closed filtering, which would break system-source rows and login-flow writes); the only read path is the admin audit endpoint whose service applies an explicit mandatory tenant predicate, covered by a dedicated cross-tenant leak test.

**Append-only at three levels:** no update/delete code path; per-dialect triggers in the Alembic migration (Postgres plpgsql `RAISE EXCEPTION 'ATLAS_AUDIT_APPEND_ONLY'` on UPDATE OR DELETE; SQLite BEFORE UPDATE/BEFORE DELETE `SELECT RAISE(ABORT,'ATLAS_AUDIT_APPEND_ONLY')`); on Postgres additionally `REVOKE UPDATE, DELETE` from the app role. `core_audit_log` is excluded from capture.

**Bulk-write guard:** the `do_orm_execute` hook raises if an ORM bulk `update()`/`delete()` targets an `AuditMixin` mapper, so audit gaps become hard errors; the journal posting flow complies because it mutates loaded line objects (see D-017), and v1 policy is that services mutate auditable entities via loaded objects. Per-field diff values are capped with a truncation marker.

**Rationale.**
Session events are the only layer that sees true before/after values and service-internal writes (event-handler postings); middleware is the only layer that knows transport facts. The split capture fixes a real correctness hole in the draft: attribute history is unreliable after flush, while generated PKs don't exist before it — capturing updates/deletes pre-flush and inserts post-flush gets both right. Same-transaction writes make the audit trail exactly as trustworthy as the ledger. Trigger-based append-only is provable in CI on SQLite.

**Rejected alternatives.**
- HTTP-middleware-only auditing: no before/after diffs, misses event-bus side effects.
- Postgres-only OLD/NEW row triggers: invisible to SQLite CI, per-table duplication.
- Single-phase `before_flush` capture (PKs missing) or single-phase `after_flush` capture (history unreliable): each wrong for half the cases — the split is the fix.
- Outbox/async audit writer: breaks atomicity.

**Risks & mitigations.**
- `after_flush_postexec` must use Core insert only (ORM adds would dirty the unit of work) — pinned by a test auditing rows across a multi-flush transaction.
- ORM bulk writes bypass flush events — converted to errors by the `do_orm_execute` assertion rather than silent gaps.
- Diff JSON of large text columns bloats the table — bounded by the truncation cap.

---

## D-011 — Domain-event bus (collect-then-dispatch, in-transaction)

**Decision.**
`core/events.py` defines `DomainEvent` (frozen Pydantic v2 model, ClassVar `key` like `'sales.order.shipped'`, fields `tenant_id` + `occurred_at`), an `EventBus` Protocol with `publish(session, event)`, a `@subscribe(key)` decorator, and `InProcessEventBus`.

**Semantics:** services call `bus.publish(session, event)`, which appends to a FIFO buffer in `session.info['pending_events']` — no immediate dispatch. The buffer is drained by ONE shared unit-of-work helper `run_in_uow()` in `core/db.py`, used both by the request session dependency in `core/deps.py` and by `seed.py`/CLI flows (so seed and HTTP get identical event semantics): after the service returns and before commit, pop events FIFO and run each handler synchronously, passing `(event, session)` so handlers write into the SAME transaction; handlers may publish further events appended to the same queue (breadth-first), with a hard cap of 50 dispatches per transaction raising `EventCycleError`.

**Handler order is deterministic:** registration order = the fixed module import order in `main.py`'s app factory (finance, inventory, procurement, sales, …). Any handler exception propagates, the whole transaction rolls back, the API returns the error envelope — deliberately NO per-handler isolation: if the COGS posting fails, the goods issue must not commit.

**Placement:** handlers live only in `modules/<m>/handlers.py` via `@subscribe` and import event classes from the publishing module's `events.py` — recorded in DECISIONS.md as an explicit STRUCTURE §5 amendment: `events.py` joins `queries.py` as a sanctioned cross-module import because it is declarative-only (Pydantic event definitions, no logic, no models); this also covers `finance/handlers.py` importing "upward" from `inventory/events.py`, which is acceptable precisely because `events.py` carries no behavior.

**Audit interplay:** handler writes are captured by the audit flush listeners automatically since they share the session. Non-transactional side effects (email, webhooks) are banned from this bus; the seam for them is a later after-commit hook, recorded now in DECISIONS.md. **Swap path:** a future `TransactionalOutboxBus` implements the same Protocol, writing `core_event_outbox` rows (key + JSON payload) in the same transaction for a relay — zero module changes.

**Rationale.**
Dispatch-in-transaction is the only semantics upholding CLAUDE.md rules 6+8: cross-module financial effects (goods issue → COGS journal) must be all-or-nothing with their trigger, and a sync in-process bus sharing the session gives exactly-once atomic causality with no outbox machinery in v1. Buffering until the service returns means handlers observe settled aggregate state. Deterministic ordering makes ledger line order and test output reproducible. The single `run_in_uow` drain point closes the gap where seed-created documents would otherwise skip COGS/docflow side effects.

**Rejected alternatives.**
- After-commit dispatch: a crashed handler leaves shipped stock with no COGS posting and no remediation — unacceptable without outbox+retry, which is post-v1.
- Publish-time immediate dispatch: handlers interleave with the publisher's half-finished writes.
- Per-handler catch-and-continue: converts consistency bugs into silent divergence.
- Celery/background handlers: loses the transaction and adds forbidden infrastructure.
- String-key-only events without importable classes: loses typing for no architectural gain since `events.py` is declarative.

**Risks & mitigations.**
- Long synchronous chains extend transaction hold time (numbering row locks, SQLite writer lock) — bounded by the depth cap, thin handlers (post + publish only, no external I/O), and a per-dispatch debug log.
- A handler needing foreign-module data must use that module's `queries.py`, never the session against foreign models — enforced by import linting in CI.

---

## D-012 — Document registry, flow links, and gapless numbering (merged)

**Decision.**
One subsystem in `core/docflow.py` + `core/numbering.py`, because registration timing and number claiming are inseparable.

**Registry `core_documents`:** id uuid PK, tenant_id, doc_type (namespaced constant like `'sales.order'`, `'fin.journal_entry'`, declared in module `constants.py` and collected in a core registry), doc_no text NULLABLE, status, created_at; partial unique index on (tenant_id, doc_type, doc_no) declared with BOTH `postgresql_where=doc_no.isnot(None)` and `sqlite_where=...` (partial indexes work on both engines but each needs its dialect kwarg); UNIQUE(tenant_id, id) to serve composite tenant FKs. Every business document table carries `document_id uuid NOT NULL UNIQUE` FK via `DocumentMixin`, created by `docflow.register(session, doc_type, doc_no=None)` in the creating service.

**Edges `core_doc_links`:** predecessor_id/successor_id FK → `core_documents.id`, link_type (`'fulfills'`, `'invoices'`, `'reverses'`, `'posts'`), nullable quantity/amount/currency_code for partial fulfillment, PK(predecessor_id, successor_id, link_type), CHECK(predecessor_id != successor_id), tenant composite-FK pattern.

**Traversal:** `docflow.get_chain` runs one recursive CTE per direction (`select().cte(recursive=True)`, works on PG and SQLite), depth column capped at 20, visited-path cycle guard; `GET /api/v1/core/documents/{id}/flow` returns `{nodes, edges}` for DocFlowViewer; display extras come from per-doc_type summary callbacks modules register.

**Numbering:** `core_number_sequences` (tenant_id, doc_type, year int — 0 for non-resetting, prefix, pattern, next_no, padding; PK(tenant_id, doc_type, year)). `next_document_number(session, doc_type, year=None)`:
1. `INSERT ... ON CONFLICT DO NOTHING` (PG and SQLite >=3.24);
2. atomic `UPDATE ... SET next_no = next_no + 1 WHERE ... RETURNING next_no - 1, prefix, pattern, padding` (RETURNING on PG and SQLite >=3.35; a tested SELECT-then-UPDATE fallback exists, safe under SQLite's single-writer lock);
3. format via pattern, validated at write time against a `{prefix}/{year}/{seq}` field whitelist.

**Claim-timing rule** (fixes the draft conflict between gaplessness and draft documents): a number is claimed in the transaction that makes the document PERMANENT. Documents with a draft lifecycle (journal entries) are registered with doc_no NULL at creation and numbered via `docflow.assign_number(session, document_id)` inside the posting transaction; documents permanent at creation (orders, receipts, invoices) are numbered at creation; once numbered, a document is never hard-deleted — cancellation is a status — so gaplessness is a free consequence of ACID (claim and document commit or roll back together). The registry's partial unique index is the DB backstop turning any numbering bug into a constraint violation.

Registry status is updated only via `docflow.set_status()` in the owning transaction; a reconciliation assertion runs in tests. Year rollover needs no job: the first posting of a new year inserts the new counter row on demand.

**Rationale.**
The registry turns the polymorphic (doc_type, doc_id) problem into ordinary FK integrity and makes chain traversal one generic CTE over one narrow table — the ACDOCA-era Document Relationship Browser shape. Merging numbering in fixes a real hole: the original drafts simultaneously required NOT NULL document numbers at creation and gapless counters, which means every abandoned draft journal entry burns a number; nullable doc_no + claim-at-permanence resolves it without weakening either invariant. The hot-row UPDATE is the textbook portable gapless pattern: counter increment and document are atomic, so there is no burned-number state to reconcile.

**Rejected alternatives.**
- Bare polymorphic (doc_type, doc_id) link pairs: no FK enforcement, per-type join fan-out.
- Per-table FK links only: chain traversal needs N module-aware queries in core, violating core-imports-nothing.
- Postgres SEQUENCE/SERIAL: non-transactional (gaps by design), not per-tenant, nonexistent on SQLite.
- `SELECT ... FOR UPDATE` for the counter: the bare atomic UPDATE achieves the same row lock in one portable statement.
- Separate draft number ranges: two numbering semantics to explain and audit.
- Materialized closure table: premature, chains are <10 nodes.

**Risks & mitigations.**
- Dual-write discipline (business row + registry + links in one transaction) — mitigated by `DocumentMixin`'s NOT NULL document_id (insert fails without registration) and a shared test helper asserting chain integrity per module happy path.
- The counter row serializes concurrent posting of one doc_type per tenant — milliseconds at v1 scale; the documented later path (cached ranges for non-legal doc_types) only changes `numbering.py`.
- Convention: claim numbers as late as possible in the service to shorten lock hold.

---

## D-013 — Idempotency keys (reservation, atomic completion via route capture)

**Decision.**
Table `core_idempotency_keys`: tenant_id, key (client `Idempotency-Key` header, max 200 chars), endpoint (METHOD + route template), request_hash (sha256 of the request TARGET — `path?query` — a newline, then the raw body; the target is in the hash because an action route's body is empty and its identity is entirely in its path, **D-071**), status (`'in_progress'`|`'completed'`), response_status int nullable, response_body JSON nullable, created_at, completed_at; PRIMARY KEY (tenant_id, endpoint, key).

**Two-phase flow** with an explicit fix to the draft's broken epilogue (a FastAPI dependency can never see the route's serialized response, and writing 'completed' after commit would break atomicity):

- **Phase 1.** The `idempotency_guard()` dependency in `core/deps.py` opens a SEPARATE short-lived session from the sessionmaker, INSERTs the (tenant, endpoint, key, request_hash, 'in_progress') row and COMMITs immediately so concurrent duplicates collide on the PK (PG unique index arbitrates; SQLite's single-writer lock serializes). On conflict it reads the existing row:
  - `'in_progress'` younger than 5 min → 409 `'idempotency_in_progress'`;
  - `'in_progress'` stale → take over via compare-and-swap on created_at;
  - `'completed'` with matching request_hash → REPLAY the stored response_status+response_body verbatim with header `Idempotency-Replayed: true`, no business logic;
  - `'completed'` with different hash → 422 `'idempotency_key_reuse'`.
- **Phase 2.** The dependency yields an `IdempotencyRecorder` bound to the request's business session; the route handler's last line is `return idem.capture(read_schema)` — `capture()` does `model_dump_json` on the exact schema FastAPI will serialize, stages `UPDATE core_idempotency_keys SET status='completed', response_status=..., response_body=..., completed_at=now()` on the BUSINESS session, and returns the schema unchanged, so the unit-of-work commit atomically persists document + replay record (the cardinal invariant: a replayable response exists iff the document exists).

**Fail-closed:** the guard's teardown (dependencies exit in reverse order, so it runs before the session dependency commits) raises `internal_error` if the handler completed a 2xx path without calling `capture()`, rolling everything back — the one-liner cannot be forgotten silently. On business exception/rollback, a cleanup transaction deletes the reservation so the client may retry the same key.

**Required** (400 `'idempotency_key_required'` if header missing) on every endpoint creating a financial or stock document: journal post, AP/AR invoice create, payment create/run, goods receipt/issue, stock transfer, count posting, delivery create/post, customer invoice create, production order confirm/finish, RMA credit note. Optional on master-data creates. Rows expire after 24 h; purge runs in the maintenance command and lazily on collision with an expired row.

**Rationale.**
PK-arbitrated reserve-then-execute is the only race-proof pattern on both engines without advisory locks. The `capture()` redesign is the load-bearing fix: storing the response from middleware after commit leaves a crash window where the document is committed but no completed row exists, so a stale takeover would double-execute; staging the completed UPDATE on the business session closes that window completely. Hash comparison distinguishes safe retries from client bugs; endpoint scoping makes one-UUID-per-form-submission safe in the frontend.

**Rejected alternatives.**
- Single-transaction reserve+execute: concurrent duplicates both proceed and fail confusingly at commit, and on Postgres the second blocks on the row lock for the first's full business duration.
- Middleware-captured response written after commit: breaks the atomicity invariant (rejected explicitly — this replaced the draft's vague "dependency epilogue").
- Redis keys: forbidden infrastructure.
- Natural-key-derived idempotency: not generalizable.
- Global (tenant+key) scope: one client key-reuse bug replays the wrong endpoint's response.

**Risks & mitigations.**
- Replayed responses are stale representations if the document changed after creation — accepted Stripe semantics; clients re-fetch by id.
- Stale-takeover double-execution if the original worker is alive-but-slow past 5 min — narrow: the original's completed UPDATE runs `WHERE status='in_progress' AND created_at` matches, so the loser's commit fails the CAS and rolls back; window documented.
- Phase-1 real COMMIT requires the test harness to support genuine commits — satisfied by the per-test database-copy strategy (see D-025).
- Response bodies bloat the table — bounded by 24 h expiry.

---

## D-014 — API envelope (keyset pagination + error shape + DB-guard error translation)

**Decision.**
**List envelope** in `core/schemas.py`: `{"items": [...], "next_cursor": str|null, "limit": int}` — no total counts (a separate aggregate endpoint serves dashboards).

**Keyset (seek) pagination only, never OFFSET:** every list orders by a whitelisted sort column plus `id` as mandatory unique tiebreaker (e.g. `ORDER BY created_at DESC, id DESC`); fetch limit+1 rows (default 50, max 200); emit next_cursor from the last returned row when limit+1 arrived. **Cursor:** `base64url(JSON)` of `{"v":1, "k":[last sort value ISO-serialized, last id], "s":"created_at:desc", "q": sha256-prefix of normalized filters}`; opaque to clients, validated server-side — v, s, q must match the current request (mismatch → 400 `'cursor_invalid'`); seek predicate written in the expanded portable form `sort_col < :k0 OR (sort_col = :k0 AND id < :k1)` because SQLite lacks mixed-direction row-value comparison. One generic helper `paginate(session, stmt, sort, cursor, limit)` lives in `core/db.py` (cursor codec + envelope models in `core/schemas.py`); module routers never hand-roll pagination.

**Error envelope** on every non-2xx: `{"error": {"code", "message", "details": list|null, "request_id"}}`; codes are machine-readable, dot-namespaced for domain rules (`'finance.period_closed'`, `'finance.journal_unbalanced'`, `'idempotency_key_reuse'`) and generic for transport (`'validation_error'`, `'not_found'`, `'permission_denied'`, `'unauthorized'`, `'conflict'`, `'internal_error'`). `core/exceptions.py`: `AtlasError` hierarchy (NotFoundError→404, PermissionDeniedError→403, ConflictError→409, DomainRuleError(code, message)→422, TenancyError→403), handlers for AtlasError, RequestValidationError (code `'validation_error'`, details flattened to `[{field, message, type}]`), and a catch-all 500 logging request_id.

**Cross-decision glue (added):** a `DBAPIError` translator in the same file maps trigger-raised tokens to envelope codes — it matches the `'ATLAS_'` substring across IntegrityError, OperationalError, and generic DBAPIError because SQLite `RAISE(ABORT)` surfaces as IntegrityError while asyncpg plpgsql RAISE surfaces differently: `ATLAS_PERIOD_CLOSED`→`'finance.period_closed'` 422, `ATLAS_UNBALANCED_ENTRY`→`'finance.journal_unbalanced'` 422, `ATLAS_POSTED_IMMUTABLE`→`'finance.entry_immutable'` 422, `ATLAS_AUDIT_APPEND_ONLY`→`'internal_error'` 500 — so the DB backstops surface through the same envelope as service checks, pinned by tests on both engines. `request_id` comes from the audit middleware's `RequestContext` and is echoed as `X-Request-Id` on every response.

**Rationale.**
Keyset pagination is O(page) at any depth and stable under concurrent inserts — the ERP norm for ledger browsing — and works identically on both engines with the expanded predicate. Fingerprinting sort+filters into the cursor catches the classic changed-filters-mid-pagination bug. One error shape with machine codes gives `apiClient.ts` a single error path and lets tests assert codes; the trigger-token translator is what makes "enforced at service AND DB level" present a uniform API face instead of leaking raw 500s when a backstop fires.

**Rejected alternatives.**
- OFFSET/LIMIT: linear degradation and phantom/duplicate rows under concurrent posting.
- HMAC-signed cursors: the seek values are data the client already saw; fingerprint validation already rejects malformed use.
- RFC 7807 problem+json: fine standard, but the single prescribed envelope is simpler and the constraint says "consistent error envelope".
- Total counts per page: `COUNT(*)` over million-row journals per request.

**Risks & mitigations.**
- No jump-to-page-N — accepted; the DataGrid uses infinite scroll/next-page semantics.
- Sorting by mutable columns can re-show moved rows — default sorts use immutable created_at/doc_no.
- Each whitelisted sort column needs a composite index — the per-endpoint whitelist is small and indexes are declared beside it.

---

## D-015 — Money and quantity representation (exact on both engines)

**Decision.**
Three TypeDecorators in `core/models.py`: `MoneyType`, `QuantityType` (PG NUMERIC(18,6); SQLite INTEGER storing Decimal × 10^6 micro-units) and `RateType` (PG NUMERIC(20,10); SQLite INTEGER × 10^10), converting to/from `decimal.Decimal` in `process_bind_param`/`process_result_value`. This explicitly supersedes D-003's "plain Numeric" wording: SQLAlchemy's `Numeric` on SQLite round-trips through float and silently loses precision, which would make the exact-sum DB triggers and tests nondeterministic.

- **Aggregations** always go through SQLAlchemy Core expressions (`func.sum(JournalLine.functional_debit_amount)`) so the argument's type propagates and result conversion applies on both backends; raw textual SQL against money columns is banned in `app/` (grep gate; tests exempt).
- **Python:** only `Decimal` represents money/quantities; Pydantic v2 schemas declare `Decimal` fields, JSON-serializing as strings (Pydantic JSON-mode default); the frontend types money as `string` and formats exclusively in `lib/format.ts`.
- **Rounding:** amounts quantize at the posting/pricing boundary to the currency's decimal_places from `fin_currencies` (ISO 4217: JPY=0, USD=2, BHD=3) via `Decimal.quantize(ROUND_HALF_UP)`; stored journal amounts never carry sub-minor-unit digits despite scale-6 headroom; unit prices/costs and FX rates keep full scale.
- **Allocation:** a single `allocate(total, weights) -> list[Decimal]` largest-remainder helper plus quantize helpers live in `core/money.py` — a new flat core file recorded in DECISIONS.md as a STRUCTURE §2 amendment (one file per cross-cutting concern) — used by tax splits, payment allocation, cost allocations, AND functional-currency balancing in journal posting, so parts always sum exactly to totals everywhere.
- **Quantities** use scale 6 for UoM/FIFO math; display precision is frontend-only.
- **Trigger discipline:** hand-written trigger SQL performs only comparisons and SUMs on the stored representation (integers on SQLite, NUMERIC on PG) — never division or scaling — so the asymmetric storage stays semantically identical where it matters.

**Rationale.**
The financial engine's DB-level invariants (balance trigger, one-side CHECK, valuation math) are only meaningful if storage is exact on BOTH backends; integer micro-units are the standard exact representation where a true decimal type is absent. ROUND_HALF_UP matches commercial/SAP practice on user-facing documents. Centralizing largest-remainder in `core/money.py` guarantees the journal's functional-balance mechanism and every split use the same arithmetic — the drafts had it in two places with slightly different semantics.

**Rejected alternatives.**
- Plain `sa.Numeric` everywhere: float round-trips on SQLite break exact trigger sums.
- TEXT decimals on SQLite: `SUM()` over TEXT does float math.
- ROUND_HALF_EVEN: statistically nicer, but surprises users reconciling invoices/tax and diverges from commercial practice.
- Integer minor units on Postgres too: NUMERIC is native, exact, and keeps psql/BI-friendly raw SQL.

**Risks & mitigations.**
- Dialect-asymmetric storage means per-dialect trigger SQL — bounded by the comparison-and-SUM-only rule and bypass tests on both backends.
- SQLite int64 caps amounts around 9.2e12 currency units at scale 6 — ample for demo/tests; PG runtime has full NUMERIC range.
- A future trigger needing arithmetic beyond SUM must be written per-dialect with explicit review.

---

## D-016 — Custom fields: core-owned JSONB + metadata registry (ownership fixed)

**Decision.**
**Ownership fix:** the draft put the registry and validator in `modules/industry`, which forces finance/inventory/hr services to import industry — an upward dependency violating STRUCTURE §5 (finance is the bottom of the import order); the parity doc itself assigns "metadata-driven field extensibility" to core. Therefore:

**Registry table `core_custom_field_defs`** (id, tenant_id, entity_key like `'inventory.item'`, field_key validated by `^[a-z][a-z0-9_]{0,49}$`, label, field_type enum TEXT|NUMBER|DECIMAL|BOOLEAN|DATE|SELECT, is_required, options JSON for SELECT, validation JSON `{min,max,regex,max_length}`, display_group, display_order, is_active; UNIQUE(tenant_id, entity_key, field_key)) and its logic live in `core/custom_fields.py` — a new flat core file recorded in DECISIONS.md as a STRUCTURE §2 amendment.

It exposes:

- `custom_fields_column()` returning `MutableDict.as_mutable(sa.JSON(none_as_null=False).with_variant(postgresql.JSONB(), 'postgresql'))`, NOT NULL server_default `'{}'`, applied by every extensible entity (item, vendor, customer, journal-entry header, sales/purchase docs, employee, equipment);
- `validate_custom_fields(session, tenant_id, entity_key, payload) -> dict`, called by owning-module services on create/update: loads active defs (per-request cached), rejects unknown keys, enforces required-on-create, coerces per type — DATE as ISO-8601 string, DECIMAL as string parsed via `Decimal` (never JSON float, consistent with D-015), NUMBER int, BOOLEAN bool, SELECT membership.

Defs are WRITTEN by industry-template application at provisioning and by an admin CRUD endpoint (`/api/v1/admin/custom-field-defs`) — both call core service functions, keeping data ownership at the platform level while templates supply content. Pydantic schemas type the field `custom_fields: dict[str, Any] = {}`; the service validator is the gate.

**Report builder** reads defs via core and builds portable expressions with `Model.custom_fields['key'].as_string()/.as_integer()/.as_boolean()` (renders `->>` on PG, `JSON_EXTRACT` on SQLite); DECIMAL sort/aggregation casts through Numeric on PG; on SQLite uses CAST to REAL and is documented display-grade. Keys are flat top-level scalars only (registry enforces no nesting). Optional Postgres-only GIN indexes ship in dialect-branched Alembic migrations when a template declares searchable fields; the SQLite arm is a no-op.

**Rationale.**
One nullable-free JSON column per entity keeps migrations trivial when templates add fields; routing validation through the owning service preserves service-layer-owns-logic; and moving the registry to core resolves the dependency inversion cleanly — modules import core freely, so every module can validate without touching industry. The portable JSON path API confines all PG/SQLite JSON divergence to two call sites.

**Rejected alternatives.**
- Industry-module ownership (the draft): upward imports from finance/inventory — a hard STRUCTURE violation; rejected outright rather than "interpreted around".
- EAV table: row explosion, painful reports.
- Per-field ALTER TABLE: per-tenant DDL is operationally dangerous and unexpressible in linear Alembic history.
- Dynamic per-tenant Pydantic models: runtime model building for zero gain over a dict validator.
- DECIMAL values as JSON numbers: floats by another name.

**Risks & mitigations.**
- Custom fields are invisible to DB constraints — accepted: they are descriptive/reporting fields by design; anything participating in financial invariants must be a real column (rule recorded in `docs/modules/industry.md`).
- Field deactivation orphans stored values — `is_active` soft-deactivation only, never hard delete.
- `JSON_EXTRACT` vs `->>` nested-value divergence — moot under the flat-scalar restriction.

---

## D-017 — Universal journal schema, posting protocol, and reversal

**Decision.**
`modules/finance/models.py`.

**Header `fin_journal_entries`:** id `sa.Uuid` app-generated, tenant_id, entry_number text NULLABLE with partial unique index (tenant_id, entry_number) WHERE entry_number IS NOT NULL — FIXED from the draft's NOT NULL: numbers are claimed at POSTING per the D-012 claim-timing rule so abandoned drafts cannot burn gapless numbers; document_type enum (MANUAL, AP_INVOICE, AR_INVOICE, PAYMENT, COGS, FX_REVAL, DEPRECIATION, REVERSAL, …), status DRAFT|POSTED|REVERSED, posting_date, fiscal_period_id FK, currency_code (one transaction currency per entry; cross-currency events become multiple entries), functional_currency_code, exchange_rate RateType, description, posted_at, posted_by_user_id, reversal_of_entry_id self-FK UNIQUE, reversed_by_entry_id self-FK, DocumentMixin document_id. REMOVED from the draft: the header idempotency_key column — idempotency has exactly one home, `core_idempotency_keys` (two uncoordinated mechanisms invite divergence).

**Lines `fin_journal_lines`:** id, tenant_id, entry_id FK, line_number (UNIQUE(entry_id, line_number)), account_id NOT NULL, nullable dimension FKs on every line (cost_center_id, profit_center_id, wbs_element_id, item_id, vendor_id, customer_id as typed FKs, warehouse_id, tax_code_id), quantity QuantityType + uom_code, MoneyType amount pairs debit_amount/credit_amount (transaction) and functional_debit_amount/functional_credit_amount, all NOT NULL DEFAULT 0; denormalized posting_date, fiscal_period_id, is_posted for projections.

**DDL:** named CHECK `ck_fin_journal_lines_one_side`: `(debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0)`; companion CHECK that functional amounts are non-negative, not both positive, and on the same side as the transaction side (functional zero allowed).

**Functional balance fix:** the draft's separate rounding-difference line is impossible — a functional-only line has zero transaction amounts and violates the mandated one-side CHECK — so the residual functional cent from translation is absorbed into the largest line's functional amount via `core/money.py` `allocate()` (largest-remainder), making functional sums balance with no special lines.

**Balance backstop:** per-dialect trigger on `fin_journal_entries` firing on the DRAFT→POSTED UPDATE, SUM-checking debits == credits over the entry's lines in BOTH currency pairs, raising `ATLAS_UNBALANCED_ENTRY` (plpgsql RAISE / SQLite `RAISE(ABORT)`) — exact on both engines per D-015.

**Immutability:** BEFORE UPDATE/DELETE on lines raise `ATLAS_POSTED_IMMUTABLE` when the parent is POSTED; BEFORE INSERT on lines raises when the parent is already POSTED; BEFORE DELETE on POSTED headers raises; BEFORE UPDATE on POSTED headers raises UNLESS the only change is reversed_by_entry_id NULL→value plus status POSTED→REVERSED (explicit column-by-column OLD/NEW comparison in the WHEN clause, dedicated tests).

**Posting protocol** (two explicit flushes — FIXED: the unit of work does not guarantee cross-table UPDATE order, so a single flush could update the header to POSTED before the line updates and trip the line-immutability triggers): the service loads the entry WITH all lines (needed anyway to validate sums in both currencies), validates balance and period, calls `docflow.assign_number()`, mutates the LOADED line objects (is_posted=True, posting_date, fiscal_period_id) — loaded-object mutation, never bulk `update()`, which both respects the audit bulk-write assertion and keeps diffs audited — then `session.flush()`; then sets header status=POSTED/posted_at/posted_by and flushes again (balance + period triggers fire here); then publishes `finance.journal.posted`; audit rows ride the same transaction automatically.

**Reversal:** `post_reversal(entry_id, reversal_date, reason)` creates a NEW entry (document_type=REVERSAL, fresh number claimed at its posting, reversal_of_entry_id set) with every line copied dimension-identical and debit/credit swapped in BOTH currencies using the original frozen functional amounts (no re-translation), posted into an open period; then sets original.reversed_by_entry_id + status=REVERSED (the single sanctioned header mutation); both linked in docflow with link_type `'reverses'`. No deletes, no in-place edits, ever.

**Rationale.**
This is the ACDOCA pattern the parity doc declares load-bearing: one append-only line table carrying all FI and CO dimensions so every report is a projection. The status-transition trigger is the only portable row-spanning balance guarantee on both backends and fires exactly once when the invariant must hold. The three fixes (nullable entry_number, largest-remainder functional balancing, two-flush + loaded-object posting) each repair an internal contradiction in the drafts: gapless-vs-draft numbering, the rounding line vs the one-side CHECK, and flush ordering vs the immutability triggers / audit bulk-write assertion.

**Rejected alternatives.**
- Signed single amount column: the constraint hardcodes the one-side CHECK.
- Polymorphic partner (partner_type, partner_id): not FK-enforceable; the parity doc keeps separate vendor/customer masters in v1.
- Postgres DEFERRABLE constraint triggers for balance: SQLite has none; the transition trigger gives identical semantics on both.
- A functional-only rounding line: violates the mandated CHECK — replaced by largest-remainder absorption.
- Editable-until-printed entries: CLAUDE.md rule 8 mandates reversal-only correction.
- Header-level idempotency column: duplicate mechanism, removed.

**Risks & mitigations.**
- Per-dialect trigger duplication can drift — both DDL strings sit side by side in one Alembic revision and `tests/modules/finance/test_journal_db_guards.py` attempts raw-SQL UPDATE/DELETE/unbalanced-post on both backends in CI.
- The sanctioned-mutation header trigger is the subtlest piece — explicit OLD/NEW comparison plus dedicated tests.
- Loading all lines to post is O(lines) memory — acceptable; entries are bounded in practice and validation requires the lines regardless.

---

## D-018 — Period-close enforcement at DB level on both dialects

**Decision.**
`fin_fiscal_periods`: id, tenant_id, fiscal_year, period_no (1-12; 13 reserved), start_date, end_date, status OPEN|CLOSED, UNIQUE(tenant_id, fiscal_year, period_no), CHECK start_date <= end_date.

Since CHECKs cannot reference other tables, enforcement is hand-written per-dialect triggers shipped via `op.execute()` branched on `op.get_bind().dialect.name`: `trg_fin_entries_period_open` BEFORE UPDATE ON `fin_journal_entries` firing only on DRAFT→POSTED (WHEN NEW.status='POSTED' AND OLD.status<>'POSTED'), plus a BEFORE INSERT twin guarding direct inserts WHERE status='POSTED' (defense in depth — the service never inserts posted).

**Trigger body:** look up `WHERE tenant_id = NEW.tenant_id AND NEW.posting_date BETWEEN start_date AND end_date`; no row OR status<>'OPEN' → abort `ATLAS_PERIOD_CLOSED`. Postgres: one plpgsql function `fin_assert_period_open()` attached by two CREATE TRIGGERs. SQLite: `SELECT RAISE(ABORT,'ATLAS_PERIOD_CLOSED') WHERE NOT EXISTS (SELECT 1 FROM fin_fiscal_periods p WHERE p.tenant_id=NEW.tenant_id AND p.status='OPEN' AND NEW.posting_date BETWEEN p.start_date AND p.end_date)`.

The entry's stored fiscal_period_id is service-resolved from posting_date while the trigger re-derives by date, so the two cannot disagree and a service bug attaching a wrong period is caught.

**Service layer** (`finance/service/periods.py`) performs the same check first, raising PeriodClosedError → 422 `'finance.period_closed'`; the trigger is the bypass-proof backstop, surfaced through the core DBAPIError translator which matches the `ATLAS_` token across IntegrityError/OperationalError/DBAPIError (SQLite `RAISE(ABORT)` surfaces as IntegrityError, asyncpg RAISE differently — the matcher is exception-class-agnostic by design, pinned by tests on both engines).

Close/reopen are permission-gated service actions (`'finance.period.close'`/`'finance.period.reopen'`), audited; close refuses while DRAFT entries dated in the period exist (service-level check). Reversals obey the same trigger — reversing into a closed period is impossible by construction; the FX revaluation run additionally validates up front that the NEXT period is open because it posts its auto-reversal there (see D-019).

**Rationale.**
CLAUDE.md rule 8 demands rejection at service AND DB level; triggers are the only mechanism on BOTH backends that can consult another table at write time, and firing on the status transition keeps draft editing cheap and runs the check exactly once per posting. Date-based re-derivation in the trigger closes the wrong-period-id-attached hole. The `ATLAS_` token gives the exception mapper a stable dialect-independent contract.

**Rejected alternatives.**
- Postgres-only DB enforcement with service-only SQLite: the test suite runs on SQLite, so the DB guarantee would be untested where tests live.
- FK to a (tenant, period, 'OPEN') key broken at close time: closing would mutate/delete a referenced row and retroactively invalidate posted entries' FKs.
- Service-only enforcement: excluded by hard constraint.
- Trigger checking only the stored fiscal_period_id's status without date re-derivation: weaker — a service bug could attach a wrong open period to an out-of-range date.

**Risks & mitigations.**
- Trigger-vs-service semantic drift over time (e.g., a future period-13 rule added only in Python) — rule: every period-semantics change ships service code + a new trigger revision + the raw-SQL bypass test in one PR.
- Exception-class differences across drivers — handled by substring matching in the core translator, pinned by tests on both engines.

---

## D-019 — FX handling (rates, posting-time translation, realized vs unrealized)

**Decision.**
`fin_exchange_rates`: id, tenant_id, rate_date, from_currency_code, to_currency_code, rate_type SPOT|CLOSING, rate RateType NUMERIC(20,10), UNIQUE(tenant_id, rate_date, from, to, rate_type). `finance/service/fx.py` `get_rate()`: most recent rate with rate_date <= on_date; missing → MissingExchangeRateError (postings never guess; inverse pairs are either stored or computed explicitly in the service with documented 10-dp rounding).

**Translation happens exactly once, at posting:** the posting service resolves the SPOT rate for posting_date (or a caller-supplied rate stored on the header), computes functional debit/credit per line quantized half-up to functional-currency decimals, and balances the residual functional cent by largest-remainder absorption into the largest line (`core/money.py` `allocate` — FIXED from the draft's separate rounding line, which would violate the one-side CHECK; the configured rounding-difference account in `fin_posting_defaults` remains in use for real-amount adjustments like moving-average zero-quantity flush); posted lines are never re-translated (immutability triggers guarantee it).

**Realized FX** arises only at clearing: the open-item clearing service (`finance/service/payments.py`) computes, per cleared document, functional-at-invoice-rate minus functional-at-payment-rate over the cleared transaction-currency amount and posts the difference inside the same clearing journal entry to fx_realized_gain/fx_realized_loss accounts mapped via `fin_posting_defaults` (per-tenant rows keyed by purpose string).

**Unrealized FX:** `run_fx_revaluation(period_id, rate_date)` — for each foreign-currency open item (uncleared AP/AR) and foreign-currency bank/cash account, compute open transaction-currency balance × CLOSING rate minus carried functional value; post ONE entry per (currency, account) delta (document_type=FX_REVAL): balance-sheet adjustment account against fx_unrealized_gain/loss, and immediately post its reversal dated day 1 of the next period (auto-reversing) — the run therefore VALIDATES UP FRONT that the next period exists and is OPEN, because the period trigger will reject the reversal otherwise (added; the draft was silent and would fail mid-run). Run bookkeeping in `fin_revaluation_runs` (tenant_id, period_id, rate_date, status, entries linked via docflow); re-running first posts reversals of the previous run's entries (append-only, never delete), then reposts.

**Rationale.**
Matches the parity contract: transaction + functional currency, rates table, realized/unrealized FX accounts. Posting-time translation with frozen functional amounts is what makes the universal journal projectable without rate joins and keeps historical statements immutable. Auto-reversing unrealized adjustments keep clearing-time realized math based on original invoice rates with no double counting. Purpose-keyed posting defaults keep account wiring data-driven.

**Rejected alternatives.**
- Report-time translation: every projection needs rate joins and history mutates when rates are edited; the parity doc's later path (extra frozen currency columns) presumes posting-time translation.
- Persistent revaluation rebasing item carrying values: requires per-item revaluation history for correct clearing math; auto-reversal achieves correct statements with far less machinery.
- Base-currency triangulation: one functional currency per tenant in v1, direct pairs suffice.
- A functional-only rounding line: violates the one-side CHECK (replaced by largest-remainder).

**Risks & mitigations.**
- Clearing and revaluation must share open-item granularity or gains double-count — guaranteed by auto-reversal (revaluation never touches carrying values) plus a test proving invoice → revalue → reverse → pay nets exactly the invoice-vs-payment-rate difference.
- Missing rates block operational posting — intended fail-loud; `seed.py` seeds rates.
- Next-period-open precondition couples revaluation to period management — surfaced as a clear 422 before any entry posts.

---

## D-020 — Inventory costing (moving average + FIFO layers, same-transaction COGS, no negative stock)

**Decision.**
`inv_items.costing_method` enum MOVING_AVERAGE|FIFO, defaulted from item category, changeable only while no stock exists. Quantity SSOT remains `inv_stock_moves`.

**Moving average:** `inv_item_valuations` (tenant_id, item_id, warehouse_id, on_hand_qty QuantityType, avg_unit_cost full-precision, total_value MoneyType; UNIQUE(tenant_id, item_id, warehouse_id)), updated in the SAME transaction as the move under `select(...).with_for_update()` — on Postgres this takes the row lock serializing concurrent movers; on SQLite the dialect silently OMITS the FOR UPDATE clause (it is a no-op, not an error — clarified from the drafts' contradictory claims), and SQLite's single-writer lock provides equivalent serialization; the PG locking path is proven by pg-marked concurrency tests in CI.
- Receipt: `total_value += receipt_value; on_hand_qty += qty; avg_unit_cost = total_value / on_hand_qty` unrounded.
- Issue: `cogs = quantize(qty × avg_unit_cost, currency dp, HALF_UP); total_value -= cogs`; when on_hand_qty hits 0, residual total_value is flushed to the price-difference account so value and quantity never disagree.

**FIFO:** `inv_cost_layers` (id, tenant_id, item_id, warehouse_id, receipt_move_id FK, received_at, original_qty, remaining_qty with CHECK `remaining_qty >= 0 AND remaining_qty <= original_qty`, unit_cost) plus `inv_layer_consumptions` (issue_move_id, layer_id, qty, cost). Issues consume layers ordered (received_at, id) ascending under `with_for_update`, one consumption row per touched layer; COGS = sum of per-layer quantized qty × unit_cost. Reversing an issue replays consumption rows backwards onto the exact layers; vendor returns consume layers normally; customer returns create a new layer at original COGS cost.

**COGS consistency:** the in-process bus dispatches synchronously in the SAME session/transaction — inventory writes move + valuation/layer updates, publishes `inventory.stock.issued` carrying the computed cost and dimensions; `finance/handlers.py` posts the COGS journal entry (Dr COGS / Cr Inventory, dimensions copied: item, warehouse, cost center/WBS) before commit. One commit = move + valuation + journal + docflow link; a stock move can never exist without its journal entry or vice versa — explicitly recorded as the v1 decision whose future Kafka swap introduces a transactional outbox then, not now.

**Negative stock forbidden outright:** service raises InsufficientStockError pre-flight, DB CHECKs (`on_hand_qty >= 0`, `remaining_qty >= 0`) back it; no per-warehouse opt-in. **Deadlock avoidance:** any transaction touching multiple valuation rows locks in (item_id, warehouse_id) sort order.

**Rationale.**
The parity doc commits to moving average AND FIFO per item category with event-driven COGS posting. Same-transaction handling is the only design keeping stock value in the journal identical to the valuation table without reconciliation machinery, while the bus abstraction still decouples the modules at code level per CLAUDE.md rule 6. Layer consumption rows make COGS auditable per layer and reversals exact rather than recomputed. Banning negative stock makes FIFO well-defined and keeps the valuation CHECKs simple; shortage handling belongs to ATP/backorders per the parity doc.

**Rejected alternatives.**
- Async/after-commit COGS: opens a stock-vs-GL divergence window requiring reconciliation jobs that contradict the universal-journal philosophy.
- Negative stock with provisional cost and retroactive correction (Odoo-style): requires retroactive revaluation clashing with posted-entry immutability.
- Global valuation row without warehouse dimension: parity scope is multi-warehouse and transfers need per-warehouse value.
- Report-time FIFO COGS recomputation: COGS must be a posted journal fact or statements change as layers mutate.

**Risks & mitigations.**
- A finance handler bug rolls back inventory operations — intended (correctness over availability), documented for operators, tightly tested on the handler path.
- Moving-average rounding drift — absorbed by the zero-quantity flush rule, tested explicitly.
- SQLite cannot exercise true lock contention — accepted; the pg-marked tests carry that burden in CI.

---

## D-021 — Statements as pure projections + account-type model

**Decision.**
`fin_accounts` (tenant_id, code, name, account_type ASSET|LIABILITY|EQUITY|REVENUE|EXPENSE, normal_balance derived from type, is_postable, cash_flow_category nullable OPERATING|INVESTING|FINANCING, is_cash_equivalent, account_group_id FK); `fin_account_groups` (tenant_id, code, name, parent_id self-FK, sort_order) as a pure presentation hierarchy; only leaf accounts postable.

All statements build in `finance/service/statements.py` (reporting consumes via `finance/queries.py`) from ONE base aggregate over `fin_journal_lines` only — no header join, because lines denormalize tenant_id, posting_date, fiscal_period_id, is_posted (set during the posting transaction):

```python
select(JournalLine.account_id,
       func.sum(functional_debit_amount - functional_credit_amount))
.where(tenant filter, is_posted == True, date predicates)
.group_by(account_id)
```

MoneyType type propagation keeps sums exact on both backends.

- **Trial balance** = that query split into per-account debit/credit totals.
- **P&L** = REVENUE+EXPENSE over a range.
- **Balance sheet** = ASSET/LIABILITY/EQUITY cumulative to a date, with retained earnings computed on the fly as cumulative REVENUE+EXPENSE net over ALL history to the as-of date, presented as a synthetic "Current and accumulated earnings" equity line (exact by construction, since v1 has no year-end carryforward per the parity doc).
- **Cash flow (indirect)** = net income + signed deltas of non-cash balance-sheet balances between two as-of dates grouped by cash_flow_category, with the service ASSERTING reconciliation to the movement on is_cash_equivalent accounts equals zero — a built-in self-check.

**No stored totals anywhere:** no balance tables, no materialized views (CLAUDE.md rule 1).

**Performance:** composite partial index `ix_fin_journal_lines_proj` ON (tenant_id, account_id, posting_date), declared with BOTH `postgresql_where=is_posted` AND `sqlite_where=is_posted` dialect kwargs (each engine needs its own — added; the draft named only one), plus `postgresql_include=['functional_debit_amount','functional_credit_amount']` for index-only scans on PG (kwarg harmlessly ignored on SQLite). Holds sub-second to ~10M lines on Postgres. Escape hatch if scale exceeds that: an explicitly-cache-semantics materialized view refreshed from the journal (journal stays SSOT), out of v1 and gated on a DECISIONS.md entry.

The is_posted flag's agreement with header status is guaranteed by the two-flush posting protocol plus immutability triggers and asserted by a dedicated guard test.

**Rationale.**
Direct implementation of the Universal Journal rule: views are projections, totals never stored, FI/CO reconciliation eliminated by construction. Five account types + cash_flow_category is the minimal metadata from which all four statements derive mechanically; computing retained earnings from full history is what makes "no carryforward in v1" sound rather than a correctness hole. One base query keeps every statement provably consistent with the trial balance — same predicate, same index.

**Rejected alternatives.**
- Running-balance or period-totals tables updated on posting: violates CLAUDE.md rule 1 verbatim and reintroduces reconciliation.
- Account-code-range statement layout (classic SAP FSV intervals): the account_group FK hierarchy is simpler, referentially enforced, template-friendly.
- Direct cash-flow method: requires counterparty-cash tagging on every line; indirect derives from data already present.
- Materialized views in v1: premature and PG-only.

**Risks & mitigations.**
- Cumulative-from-genesis balance-sheet queries grow linearly with history until balance carryforward ships (already a parity-doc "later") — the partial covering index keeps this an index-only scan on PG, and the carryforward job slots in later without schema change.

---

## D-022 — Alembic dual-database strategy and CI matrix

**Decision.**
A single linear migration chain runs unmodified on both backends; migrations are the ONLY schema source — `Base.metadata.create_all` is banned everywhere INCLUDING tests, because triggers and raw DDL live only in migrations (tests would otherwise pass without the DB guards they claim to test). Rules:

1. `env.py` uses the async pattern (`async_engine_from_config` + `connection.run_sync(do_run_migrations)`, `asyncio.run` in the offline-safe wrapper), reads `ATLAS_DATABASE_URL`, configures `compare_type=True` and `render_as_batch=True`.
2. Every ALTER goes through `with op.batch_alter_table(...)` unconditionally — pass-through on Postgres, copy-rebuild on SQLite — which requires deterministic constraint names: `core/models.py` declares `MetaData(naming_convention={'ix':'ix_%(column_0_label)s','uq':'uq_%(table_name)s_%(column_0_name)s','ck':'ck_%(table_name)s_%(constraint_name)s','fk':'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s','pk':'pk_%(table_name)s'})`; unnamed constraints cannot be dropped in SQLite batch mode.
3. Type portability lives in the models (`with_variant` JSONB, `sa.Uuid`, MoneyType/QuantityType/RateType), so autogenerated revisions import those types from `app.core.models` and stay dialect-clean; hand review of every autogen revision is mandatory.
4. Trigger/function DDL: per-dialect string pairs side by side in the migration body under `if op.get_bind().dialect.name == 'postgresql': op.execute(PG_SQL) else: op.execute(SQLITE_SQL)`; stable names `trg_<table>_<purpose>`; upgrades DROP TRIGGER IF EXISTS then CREATE; downgrades drop. **Rule (load-bearing):** any migration that batch-alters a trigger-bearing table MUST re-execute that table's trigger DDL afterwards, because SQLite's copy-rebuild silently drops triggers — recorded in the migration template comment and caught by the guard tests, which run against the final migrated schema. Postgres-only physical extras (GIN indexes, INCLUDE columns) sit in the same dialect branch with a plain-index or no-op SQLite arm.
5. CI, single `backend` job extended: **step A** `alembic upgrade head` + full `uv run pytest -q` on SQLite (file DB); **step B** `services: postgres:16` container — `alembic upgrade head`, then `alembic downgrade base && alembic upgrade head` (reversibility proof), then `uv run pytest -q -m pg` re-exercising the DB-guard subset (journal/period/audit triggers, JSONB paths, with_for_update contention, idempotency races) on real Postgres. The `pg` marker lives on `tests/modules/finance/test_journal_db_guards.py`, period bypass tests, audit append-only tests, and inventory locking tests.

**Rationale.**
D-003 fixed the dual-backend posture; this makes it mechanical. Batch-everywhere plus a naming convention is the canonical Alembic SQLite recipe; model-level type variance makes autogenerate output portable by construction; and running the financial-guard tests on real Postgres is what turns "enforced at DB level on BOTH" from an assertion into a tested claim. The trigger-recreation-after-batch rule prevents the silent-guard-loss failure mode that would otherwise pass every test until a rebuild migration ships.

**Rejected alternatives.**
- Two migration branches per dialect: guaranteed drift, doubled review, breaks linear NNNN numbering.
- `create_all` for tests with a trigger fixture: duplicates trigger DDL outside migrations, violating single-source.
- Skipping Postgres in CI: trigger and FOR UPDATE behavior differ enough that untested-on-PG is unacceptable for the financial engine.
- Separate .sql files for trigger DDL: STRUCTURE forbids orphan files; migrations are self-contained.

**Risks & mitigations.**
- Per-test isolation against the migrated schema is owned by D-025 (template-copy pattern) — the two decisions interlock and must not drift.
- Autogen occasionally emits dialect-specific DDL despite variants — mandatory hand review per STRUCTURE §8.6 plus the dual-engine CI run catches it.

---

## D-023 — Frontend type strategy (hand-written types.ts with compile-time drift gate)

**Decision.**
Per STRUCTURE §4, each frontend module keeps a HAND-WRITTEN `src/modules/<module>/types.ts` mirroring that module's backend Pydantic Read/Create/Update/Filter schemas, snake_case preserved (no camelCase translation layer).

**Mapping conventions, fixed:** Decimal/money → `string`; date/datetime → `string` (ISO 8601); UUID → `string`; backend enums → TS string-literal unions of the UPPER_SNAKE values (`type EntryStatus = 'DRAFT' | 'POSTED' | 'REVERSED'`); nullable/Optional → `| null`; Masked fields → `T | null`. Shared envelope types (`Page<T> {items, next_cursor, limit}`, `ApiError {error: {code, message, details, request_id}}`) live once in `src/lib/apiClient.ts`.

**Drift control, two compile-time gates and zero runtime cost:**

1. `backend/openapi.json` is COMMITTED and regenerated via a Makefile target (`make openapi` calls a tiny dump entry that instantiates the app factory and writes `app.openapi()`); a backend pytest test asserts the committed file equals the live app's schema, so any schema change that forgets regeneration fails the backend CI job with a "run make openapi" message.
2. A frontend devDependency `openapi-typescript` generates a GITIGNORED `src/lib/openapi.gen.d.ts` from `../backend/openapi.json` as a pre-step of `npm run typecheck`; each module adds a `types.contract.ts` containing only type-level assertions using Expect/Equal helpers from lib (`type _ = Expect<Equal<JournalEntry, components['schemas']['JournalEntryRead']>>`) — one line per mirrored type — so tsc fails on any divergence in either direction.

Application code imports ONLY the hand-written `types.ts`; the generated file is referenced solely by contract files and is never committed (consistent with STRUCTURE §8.6: generated files are never hand-edited; here it is also never shipped). The CI frontend job's existing `npm run typecheck` therefore enforces the contract with no new job.

**Rationale.**
STRUCTURE mandates hand-written mirrors, which keeps frontend types curated and readable — but hand-written without a gate guarantees drift. Routing the gate through the committed OpenAPI document gives an explicit, reviewable contract artifact whose own freshness is enforced backend-side, while the type-level Equal assertions catch field renames, nullability changes, and enum-value drift at compile time in both directions. String-typed money/dates align with the backend's Decimal-as-string serialization and force all formatting through `lib/format.ts` per STRUCTURE.

**Rejected alternatives.**
- Fully generated committed types as the app's source: violates the hand-written mandate, bloats diffs, and produces unidiomatic deeply-nested component types.
- Runtime zod/valibot validation: a second schema source to keep in sync and runtime cost on every response; the API is first-party so compile-time checking suffices.
- No gate ("be careful"): drift is guaranteed across 13 modules.
- Comparing types via a custom AST script: reimplements what tsc's structural equality already does.

**Risks & mitigations.**
- `openapi.json` merge conflicts on parallel schema work — resolved by regenerating (`make openapi`), never hand-merging.
- Contract files add one assertion line per type — trivial, and a missing assertion is visible in review because the convention is one contract file per module listed beside `types.ts`.
- `Equal<>` on very large unions can slow tsc marginally — bounded by module-scoped contract files.

---

## D-024 — Frontend auth: in-memory access token, cookie refresh, cross-tab single-flight

**Decision.**
`src/lib/auth.ts` owns all token state. **Access token:** held ONLY in a module-scoped variable (with a subscribe hook for React state) — never localStorage/sessionStorage. **Refresh token:** never touched by JS (httpOnly cookie managed by the browser, scoped to `/api/v1/auth` per D-008). `apiClient.ts` attaches `Authorization: Bearer` from auth.ts on every call.

- **Boot sequence:** app start calls `POST /api/v1/auth/refresh` once (cookie present → new access+refresh pair, resumes the session silently; 401 → unauthenticated state, router redirects to /login).
- **Proactive renewal:** auth.ts decodes the access token's exp claim client-side (base64 decode only, no verification — it is not a trust decision) and schedules a refresh at exp minus 60 s.
- **Reactive path:** on any 401, apiClient triggers a single-flight refresh — within a tab, concurrent requests await one shared in-flight promise then retry exactly once; a second 401 after retry → hard logout.
- **Cross-tab coordination** (required because backend rotation invalidates the old refresh jti — even with the 10 s grace window, uncoordinated tabs hammering refresh is wrong): the refresher acquires `navigator.locks.request('atlas-auth-refresh')` so exactly one tab rotates, and broadcasts the new access token via `BroadcastChannel('atlas-auth')`; other tabs adopt it instead of refreshing; logout events broadcast the same way so all tabs clear state and redirect together.
- **Logout:** `POST /api/v1/auth/logout` (revokes the sid row, clears the cookie), clear memory, broadcast, `queryClient.clear()`.
- **Identity/permissions:** after any successful login/refresh-boot, fetch `GET /api/v1/auth/me` (user, tenant, permission keys) into TanStack Query; TanStack Router `beforeLoad` guards check auth.ts state and the permission set for route gating — UI-only convenience, the server remains the enforcement point.
- **Tenant selection** happens at login (tenant_slug field); the SPA never sends tenant headers — tenancy rides the JWT.

**Rationale.**
Memory-only access tokens are XSS-resistant (no persistent readable storage) and the boot-refresh makes hard reloads seamless since the httpOnly cookie persists. Single-flight + Web Locks + BroadcastChannel is the standard answer to rotation-with-reuse-detection in multi-tab SPAs: it eliminates the benign-race family revocations the backend grace window only softens. Proactive renewal avoids latency spikes and thundering 401 retries. Keeping every fetch in apiClient.ts (per STRUCTURE) means the 401/retry/refresh logic exists exactly once.

**Rejected alternatives.**
- localStorage/sessionStorage tokens: XSS-exfiltratable, explicitly rejected.
- Access token in a cookie too: makes every API call CSRF-relevant instead of just /auth.
- Per-tab independent refresh without coordination: races rotation and logs users out under normal multi-tab use.
- Service-worker token broker: strictly more moving parts for the same isolation in a v1 SPA.
- Storing permissions in localStorage for instant boot: stale-permission UI and another sync problem — /auth/me is one cheap request.

**Risks & mitigations.**
- `navigator.locks`/BroadcastChannel need modern browsers — fine for v1 scope; a no-op fallback (per-tab single-flight only) keeps Safari/old engines working with the backend grace window absorbing the residual race.
- In-memory token dies on reload — by design; boot refresh restores it.
- Clock skew breaks proactive scheduling — harmless: the reactive 401 path is the safety net.

---

## D-025 — Backend testing strategy (async fixtures, per-test DB copies, trigger tests on SQLite)

**Decision.**
pytest + pytest-asyncio with `asyncio_mode=auto`; HTTP tests use `httpx.AsyncClient` over `ASGITransport(app)` — no live server.

**Database isolation uses the TEMPLATE-COPY pattern**, deliberately replacing the draft's SAVEPOINT/join-external-transaction approach, which breaks the moment code under test performs REAL commits — and ours does by design (idempotency's separate reservation transaction, `run_in_uow` commits, numbering claims): a session-scoped fixture builds ONE migrated template SQLite file via programmatic `alembic.command.upgrade(config, 'head')` (env.py's `asyncio.run` pattern works because the session fixture runs outside any event loop); a function-scoped fixture copies that file (`shutil.copy`, ~ms) into tmp_path, builds an aiosqlite engine on the copy with the connect-event `PRAGMA foreign_keys=ON`, and overrides the app's session dependency. Every test gets a fully migrated, trigger-bearing, fresh database where real commits are allowed and nothing leaks across tests. For the pg-marked subset in CI, a fixture creates a per-test database via `CREATE DATABASE ... TEMPLATE atlas_test_template` from a once-migrated template database and drops it after — same semantics on Postgres.

**Fixtures in `tests/conftest.py`:** `tenant_factory` provisions tenant + admin user + role with named permissions through the REAL provisioning service under `system_context`, returning a handle with tenant_id and an `auth_headers(user)` helper that performs a real login; `authed_client` composes it; `permissions_context` sets the `current_permissions` ContextVar for serializer-level masking tests; module fixtures live in `tests/modules/<module>/conftest.py` per STRUCTURE §6.

**DB-guard tests** (`tests/modules/finance/test_journal_db_guards.py` etc.) deliberately use raw `session.execute(text(...))` to BYPASS the service layer — sanctioned because the CI grep gate banning `text()` is scoped to `app/`, not `tests/` — asserting that UPDATE/DELETE on posted lines, unbalanced DRAFT→POSTED, closed-period posting, and audit UPDATE/DELETE all raise with the `ATLAS_` tokens on SQLite, with the same tests re-run on Postgres via `-m pg`. The tenancy suite enumerates `Base.registry.mappers` (auto-covering new models); event-bus tests assert handler effects and rollback-on-handler-failure within one transaction; idempotency tests exercise the two-transaction reservation flow with real commits; determinism comes from explicit posting_date/anchor arguments in factories, not clock freezing.

**Rationale.**
The template-copy pattern is the single decision that makes everything else testable as designed: SAVEPOINT isolation silently converts the idempotency guard's real COMMIT into a savepoint release (changing the very semantics under test) and shares state when code opens a second session. File copies are milliseconds on SQLite and CREATE DATABASE TEMPLATE is fast on Postgres, so the cost is negligible while every test sees the exact schema migrations produce — triggers included, which is the whole point of asserting DB guards in CI. Factories going through real services means tenancy stamping, numbering, docflow, and audit are exercised by every test that touches data.

**Rejected alternatives.**
- SAVEPOINT/join-external-transaction per test (the draft): incompatible with real multi-transaction code paths and second sessions; rejected as the primary pattern.
- `create_all` + trigger fixture: duplicates DDL outside migrations and tests a schema nobody ships.
- In-memory `:memory:` SQLite: cannot be shared across connections/sessions the way the app's engine needs, and cannot be template-copied.
- One shared DB with truncation between tests: ordering-sensitive and slow on Postgres.

**Risks & mitigations.**
- Session-scoped template means schema changes require fixture cache invalidation — the template path embeds the Alembic head revision in its filename, so a new revision automatically rebuilds.
- Per-test PG database creation is slower (~100 ms each) — confined to the small pg-marked subset.
- Raw-SQL bypass tests are tightly coupled to trigger names/tokens — intentional pinning; they exist to fail when guards change.

---

## D-026 — Seed-data architecture (deterministic, per-template, three months of linked transactions)

**Decision.**
`backend/seed.py` is a CLI (argparse: `--templates` defaulting to all five seeded industry profiles, `--anchor-date` defaulting to today, `--reset`) that assumes a migrated database (Makefile target chains `alembic upgrade head`).

**Determinism:** one `random.Random(f'{template}:{anchor_date}')` per tenant — identical output for a given (template, anchor) pair; the anchor is recorded on the tenant so reruns are reproducible for bug reports.

**Provisioning phase** under `system_context()`: per template, create tenant (slug `demo-<template>`, fixed admin credentials sourced from `.env.example` values), apply the YAML industry template via the industry module's real application service — modules toggled, display labels, chart-of-accounts preset, tax codes, number-sequence patterns, system roles, custom-field defs (written through `core/custom_fields.py`).

**Transaction phase:** set the tenancy ContextVar to the tenant (NOT `system_context` — business writes must be stamped and filtered normally) and drive everything through the REAL service layer wrapped in `run_in_uow()`, never raw inserts — so numbering, docflow registration and links, domain events (goods issue → COGS), audit rows, and DB triggers all fire exactly as in production, making seed a standing integration proof.

**Script per template spans 3 calendar months ending at anchor:** master data first (items, vendors, customers, warehouses, employees, WBS elements, exchange rates including one foreign currency); then interlinked flows — procurement P2P chains (requisition → PO → goods receipt → AP invoice → payment run), sales O2C (quote → order → delivery → customer invoice → receipt, including partial shipments and one open backorder), template-specific depth (production orders with WIP postings for manufacturing; projects + timesheets for professional-services; maintenance orders for construction; quality inspection lots for healthcare/retail receiving), foreign-currency invoices plus a month-end FX revaluation run, manual journal entries, and month-end closes: periods for months 1 and 2 CLOSED via the real period-close service, month 3 left OPEN with open AP/AR items so aging, dunning, and dashboards have live data. Volumes ~100-300 documents per tenant (seconds on SQLite).

**Idempotency:** without `--reset`, seed refuses if a demo tenant exists; `--reset` hard-deletes the demo tenants by cascade — the ONLY sanctioned hard-delete path in the codebase, running under `system_context` and documented as such.

**Self-verification:** seed ends by asserting, per tenant, (a) trial balance debits == credits, (b) every created document's docflow chain traverses end-to-end, (c) inventory GL balance == sum of `inv_item_valuations` — and CI runs seed against SQLite after the test suite as a smoke gate.

**Rationale.**
Seeding through real services is the load-bearing choice: SQL-dump seeds rot with every migration and bypass exactly the invariants (gapless numbers, docflow, COGS events, period triggers) the demo exists to showcase, while service-driven seeding doubles as an end-to-end integration test the CI runs for free. Deterministic RNG + recorded anchor gives reproducible demos and bug reports without freezing real time. Closing two of three months demonstrates the period-close machinery and leaves believable open items for the operational screens.

**Rejected alternatives.**
- SQL dump / fixtures files: bypass invariants, drift with schema, undebuggable diffs.
- Faker with random seed-per-run: non-reproducible demo states.
- Seeding via HTTP API: needs a running server and auth choreography for zero added fidelity — the service layer is the contract.
- A full year of data: slower seeds for no demo value; the parity scope's reports all read well at 3 months.

**Risks & mitigations.**
- Anchor defaulting to today means runs on different days differ in dates (structure stays identical given anchor) — acceptable; CI pins a fixed anchor for the smoke gate.
- Seed duration creeps as modules land — bounded by per-tenant volume caps and the CI timing check.
- The `--reset` cascade is a footgun if pointed at a non-demo tenant — guarded by a slug prefix check (refuses anything not starting with `demo-`).


## D-075 — Background-job durability: the stale-job sweeper and its precondition

**Decision.**
`core/jobs.py` is at-most-once by construction and, before P0, *lost* jobs on process death. `submit_job` commits a PENDING row inside the caller's transaction; `schedule_job` then creates an asyncio task on the REQUEST's own event loop. A deploy, container restart or OOM kill between those two points killed the task and left the row PENDING (never picked up) or RUNNING (picked up, never finished), with nothing in the system ever reading it again. Since D-072 moved ingredient depletion — which posts COGS — onto the runner, that was a silent loss of GL postings.

**The three mechanisms, in the order they must be understood.**

1. **Handler idempotency is the precondition, not a feature.** Re-dispatching a handler that is not safe to run twice converts a LOST posting into a DUPLICATED one, which is strictly worse than the gap being closed. All seven `@register_job` handlers are audited and pinned by `tests/core/test_job_reruns.py`, whose `RERUN_VERDICTS` map fails the build if a handler is added without a stated verdict. The shared detector is a fingerprint over the three append-only ledgers (journal entries, journal lines, stock moves) — a double-post can only ever make that tuple grow, whatever module it happened in.
2. **The runner claims its row.** `_run_handler` transitions PENDING → RUNNING with a CONDITIONAL update and returns without touching the handler if it loses. This is what makes reclaiming a PENDING row safe when the original asyncio task was merely queued behind `MAX_CONCURRENT_JOBS` rather than dead.
3. **The sweep itself** (`core/job_sweeper.py`) runs on the app lifespan — once at startup, because a deploy IS a shutdown and its orphans are the common case, then every 5 minutes. It reclaims through the ordinary `schedule_job` path, so a reclaimed job restores its own tenant (D-007) and actor (D-010) and still executes inside `run_in_uow` (D-011); the sweeper itself runs no business logic.

**Thresholds and bounds.** PENDING reclaims after 10 minutes, RUNNING after 2 hours — nothing distinguishes "the process died" from "this MRP run is slow" except elapsed time, so the RUNNING window must exceed the slowest legitimate handler by a wide margin. 50 reclaims per tick keeps a post-outage backlog from scheduling thousands of tasks on an already-unhealthy system. 3 attempts (`core_jobs.attempts`, migration 0049) then the row is marked FAILED and left alone.

**Cost.** One bounded scan plus one bulk UPDATE per outcome — flat in the backlog size. Served by `ix_core_jobs_status_updated_at_unfinished`, the only index on `core_jobs` that does not lead with `tenant_id` (the scan is cross-tenant by definition) and partial on the unfinished statuses so it stays small however large the job history grows.

**Visibility.** A `failed_jobs` dashboard KPI (7-day window, gated on `admin.audit.read`) plus the pre-existing `GET /api/v1/jobs?status=FAILED`, which was already keyset-paginated and already carried the handler's error text. With the sweeper in place, "stale" collapses into "FAILED": every lost job eventually lands on that list.

**Retention.** The same tick purges `core_idempotency_keys` older than 7 days, bounded at 500 rows. One mechanism on one timer rather than two.

**Rationale.**
Reliability here had to be bought without adding infrastructure — Atlas has no queue, no cron, and no scheduler process, and introducing one for this would be a far larger change than the gap warrants. An asyncio task on the existing lifespan, re-dispatching through the existing runner, reuses every property the runner already guarantees. The genuinely hard part was never the sweep; it was proving that every handler could survive being run twice, which is why that work is a separate, earlier commit.

**Rejected alternatives.**
- A heartbeat / lease column on `core_jobs`, so a RUNNING row could be told "dead" from "slow" precisely: correct, but it makes every handler write on a timer and the two-hour window plus the handler guards cover the same ground at zero runtime cost.
- A real queue (arq/celery): the `JobScheduler` Protocol already exists as the swap seam, but adding Redis and a worker process to close a reclaim gap is not proportionate.
- Reclaiming with a per-job UPDATE so each reclaim could be individually arbitrated: quadratic in the backlog exactly when the sweep must stay cheap; the bulk UPDATE is already conditional, and the runner's claim arbitrates the rest.

**Risks & mitigations.**
- A multi-worker deploy runs one sweeper per process. Safe (every transition is conditional) but wasteful; a single-owner lease is the upgrade path if it ever matters.
- Reclaiming under a genuinely slow live runner remains possible; it is absorbed by the handler guards rather than prevented, which is why (1) above is a hard precondition.
- This is polling made reliable, not alerting: nothing pushes. The signal now sits somewhere a person already looks, which is what D-072 owed, but a property that never opens the dashboard still learns nothing.
