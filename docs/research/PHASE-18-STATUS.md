# Phase 18 (machine credential) — build status

**Verification gate closed 2026-08-14. This supersedes the "UNVERIFIED / do not merge" version of
this file, which was accurate when written.**

## The one thing that matters

**This branch is verified and, in my judgement, mergeable to `dev`.** The full suite is green, lint
is clean, eight adversarial reviews ran against it, four real defects were found and fixed, and the
plan's done-checklist is walked below with evidence for every line.

Three limitations are recorded rather than fixed. Each is on the spec's own explicit "Not taken"
list, so fixing any of them here would be scope creep against a reviewed spec, and each is pinned
by a test that fails the day the assumption changes. They are listed under **Known limits** below —
read them before merging, because the third one changes what an operator must do.

## What exists

Branch: `feat/core-api-key-credential`, cut from `dev` at `a9967da`. Sixteen commits: six build,
one build-status doc (this file), and nine from the verification gate.

| Commit | What it does |
|---|---|
| `10e109d` | T1 — `ApiKey` model + Alembic migration 0046 |
| `f62fc1e` | T2 — `mint_api_key` / `parse_api_key` in `core/auth.py` |
| `e69017c` | T3 — the API-key branch inside `get_current_user` |
| `cd41423` | T4 — admin endpoints: create, list, revoke |
| `f3a1756` | T5 — nginx `limit_req` on `/api`, keyed on the Authorization header |
| `59f8808` | T6 — D-069, `docs/api.md` operator flow, admin module guide, PROGRESS entry |
| `c98a858` | this file, in its original "do not merge" form |
| `c7344ba` | **fix** — `ApiKey` was not AuditMixin; issuing and revoking a credential wrote no audit row |
| `69e7fca` | migration 0046 pinned on both engines, plus a repo-first `alembic check` drift guard |
| `436260b` | **fix** — a scoped key could mint a key wider than itself (D-070); also carries the `deps.py` comment correction |
| `1be6750` | **fix** — mint on the tenant UUID so the query budget holds; folds the tenant `is_active` gate into the auth join |
| `173e828` | key-string parsing under fuzz and hostile input |
| `0ee0550` | tenant isolation attacked, including a negative control |
| `80777ae` | concurrency and the shared D-013 idempotency namespace |
| `56df498` | revocation, expiry, kill switches, secret leakage |

The plan it was built from: [`hospitality-build-plan.md`](./hospitality-build-plan.md), Phase 18.
The spec that plan argues from: [`hospitality-industry-plan.md`](./hospitality-industry-plan.md), Q1.

## What verified it

**Full backend suite** — `cd backend && uv run pytest -q`: **2008 passed, 20 skipped, 0 failed**
in 299s. The pre-phase baseline was 1786 passed / 20 skipped, so the branch adds 222 passing cases
(128 test functions, expanded by parametrize) and removes none — `git diff dev...HEAD -- backend/tests`
contains zero deleted `def test_` lines.

**Lint** — `cd backend && uv run ruff check .`: **All checks passed.**

**PostgreSQL** — the `pg`-marked guards skip on the default SQLite run, so they were run separately
against a real PostgreSQL 16 following CI's exact sequence (`alembic upgrade head` → `downgrade base`
→ `upgrade head` → `pytest -m pg`): **25 passed**. That exercises migration 0046 forward, all the
way back to base and forward again on the production engine, plus its composite tenant FK, its
global secret UNIQUE and its `jsonb` scopes column (D-003).

**nginx** — verified live in a container against `frontend/nginx.conf`, not by reading it.
`nginx -t` reports *syntax is ok / test is successful*. Forty rapid requests on one credential:
22 through, then `429`s. Five requests on a *second* credential immediately after: all `200`, so
the limit really is per credential and not per IP. Forty requests with no Authorization header:
all `200`, confirming D-069's recorded gap that the empty key is unaccounted. An Authorization
header padded past nginx's 255-byte key bound was **also** limited (nginx truncates the key rather
than skipping the zone), so the oversized-header bypass I went looking for does not exist.

**Eight adversarial reviews**, each of which wrote runnable tests and committed them whether or not
they found anything:

| Area | Verdict | Outcome |
|---|---|---|
| tenant isolation | holds | 28 tests, incl. a negative control that suspends the D-007 filter and asserts the forgery then *succeeds* |
| key-string parsing | 1 defect, fixed | 84 tests; 50,000-case fuzz; the `_`-delimiter collision on underscore slugs |
| query budget & contract | 2 defects, fixed | the PERFORMANCE §2 breach, and the tenant `is_active` gate the naive fix would have dropped |
| scope containment | 1 defect, fixed | 27 tests; the D-070 mint-wider-than-yourself escalation |
| audit-actor resolution | 1 defect, fixed | 10 tests; `ApiKey` was unaudited |
| lifecycle & secret leakage | holds | 18 tests; a false kill-switch claim in a code comment, corrected |
| migration 0046 | holds | 9 tests on both engines; every new assertion mutation-checked |
| concurrency & idempotency | holds | 14 tests; the shared D-013 namespace characterised and gated |

## The four defects that were real, and what closed them

1. **`ApiKey` was not `AuditMixin`** (`c7344ba`). Issuing and revoking a machine credential wrote
   no `core_audit_log` row at all, so "who issued the credential that made this change" was
   unanswerable one hop back from an audit row. The model docstring justified the omission by
   analogy to `RefreshSession`, but a `RefreshSession` is high-churn state a user's own login
   writes, while an `ApiKey` is an operator's deliberate grant of the bound user's whole permission
   set — the same escalation `UserRole` grants, and `UserRole` is audited. Fixed with `AuditMixin`
   plus `__audit_exclude__ = {"secret_sha256"}`, for the reason `password_hash` is excluded on
   `User`: the audit viewer is a different permission (`admin.audit.read`) from the one that may
   see keys. No migration needed — `AuditMixin` adds no columns.

2. **A scoped key could mint a key wider than itself** (`436260b`, recorded as **D-070**). A key
   scoped to `admin.apikey.manage` could `POST /api/v1/admin/api-keys` with `scopes: null` on its
   own bound user and walk out with that user's entire permission set. D-069's intersection bounds
   a key against its BOUND USER, and `/api-keys` is the only endpoint in Atlas that *chooses* a
   credential's permissions, so nothing bounded the new key against the PRESENTING one — scopes
   were advisory, not confining. Fixed by one defaulted field on the frozen principal
   (`CurrentUser.is_api_key`; every authorization check still reads `permissions` and nothing else)
   and a subset check on mint. Zero extra queries. Human JWT holders are deliberately untouched.

3. **PERFORMANCE §2 breach on every ETag-carrying list endpoint** (`1be6750`). See the next section.

4. **The `_` delimiter collided with underscore tenant slugs** (demonstrated in `173e828`, closed
   by `1be6750`). `parse_api_key` split on `_` with `maxsplit=2` while the ref was the tenant slug.
   The code comment justified that with "slugs are lowercase alphanumerics and hyphens", which is
   only true of the onboarding HTTP wizard — `admin.service.provision_tenant` applies no validation
   and `adm_tenants.slug` carries no constraint, so an underscore slug is reachable through the
   repo's own sanctioned provisioning path (the conftest `user_factory` uses it). A key minted on
   slug `acme_corp` parsed back as ref `acme` plus a mangled secret: dead forever, with nothing in
   any log explaining why, and it set the tenancy ContextVar to a *different* tenant before
   anything was verified. Moving the ref to the tenant UUID makes it a strict 32-char field and
   removes the ambiguity; two property tests fail if a free-text ref ever returns.

## The query-budget question — settled

**Decision: implement the UUID form. Done, in `1be6750`.**

D-069 originally claimed an API-key list request spends exactly 3 statements — slug resolve, auth
join, page — which passes PERFORMANCE §2's ≤3 with zero margin. That measurement was taken on
`/api/v1/admin/users`, **which has no collection ETag**. Every list endpoint that calls
`core/conditional.collection_etag` — most reference lists in the codebase, across inventory, sales,
procurement, manufacturing, projects and HR — is *already* at 3 under a JWT (auth + ETag aggregate +
page). Under the slug-based key those endpoints ran **4**. That is not a thin margin; it is a
breach, and it hid because the one endpoint that got measured was the one without an ETag.

D-069 named the escape hatch itself, so the fix took it: the key now carries `tenant_id.hex`, the
D-007 ContextVar is set straight from the ref with no query, and authentication costs the same
single statement a JWT costs. The choice to spend the whole budget was never really available —
it was already overspent.

Documenting-it-instead was rejected for a further reason: `backend/tests/conftest.py:140,160-163`
is explicit that the budget's one query of slack is a regression margin, not headroom. Spending it
on a fixed per-request cost would mean the *next* query anyone adds to any list path breaches, and
the person who adds it would have no idea why.

The naive form of that fix would have introduced a second defect. `find_tenant_by_slug` was doing
double duty — it was also the tenant `is_active` gate — so deleting it would have let a deactivated
tenant's keys keep working. The check now rides in the auth join
(`select(User, ApiKey, Tenant.is_active).join(ApiKey, ...).join(Tenant, ...)`), which costs no extra
statement because `Tenant` is not `TenantMixin`. This is deliberately stricter than the JWT path,
which has no tenant check at all: a JWT dies in 15 minutes, a key can live a year.

Pinned as an **exact** count, not a ceiling — a ceiling is what let the breach hide:

- `tests/core/test_api_keys.py::test_key_auth_costs_exactly_one_statement` — authentication is
  exactly one statement, that statement carries both `core_api_keys` and `core_users` in a JOIN,
  and every counted statement is a `SELECT` (the spec's "no `last_used_at` write", made mechanical)
- `tests/modules/inventory/test_items_api.py::test_list_query_budget_under_api_key_auth` — the ≤3
  budget on the three ETag-carrying reference lists that ran 4 before the fix
- `tests/core/test_api_keys.py::test_inactive_tenant_cannot_use_its_keys` — the gate that would
  have been dropped

D-069 has been rewritten to state what is now true, and to record the wrong measurement and why it
hid, so the next person does not re-derive it.

## Phase 18 done when — walked, with evidence

| Checklist item | Status | Evidence |
|---|---|---|
| Full backend suite green, including every query-count assertion | **met** | `uv run pytest -q` → 2008 passed, 20 skipped, 0 failed. Query-count assertions are in that run and include the two new exact-count tests above. |
| `uv run ruff check .` clean | **met** | "All checks passed!" Mid-review one agent reported 5 errors from another's uncommitted scratch (a `test_zzz_dump_sql.py` SQL-dump harness plus two unused imports). Both are gone: `git log --all -- "*test_zzz_dump_sql.py"` returns nothing, so the harness entered no commit, and the working tree is clean. |
| A key authenticates, is narrowed by its scopes, cannot read another tenant, and dies on revoke and on expiry — each covered by a test | **met** | authenticates: `test_api_key_authenticates`, `test_an_issued_key_authenticates`. Narrowed: `test_scopes_cannot_add_a_permission_the_user_lacks`, `test_a_scope_for_a_module_the_user_cannot_touch_is_dropped` (asserts the exact effective set through `/auth/me`). Cross-tenant: `test_key_of_tenant_a_presented_as_tenant_b_cannot_authenticate`, `test_valid_key_cannot_read_another_tenants_record_by_id`, `test_valid_key_cannot_list_or_revoke_another_tenants_keys`. Revoke: `test_revoke_bites_on_the_very_next_request`, `test_revocation_beats_the_warm_rbac_memo`. Expiry: `test_expiry_boundary_exactly_now_is_rejected` and `test_expiry_boundary_one_microsecond_later_still_authenticates` — both sides of the boundary on a frozen clock. |
| No new `system_context()` call site | **met** | `git grep -c "with system_context()"` over `backend/app`: **21 on `dev`, 21 on `HEAD`**. `git diff dev...HEAD -- backend/app` adds no line containing it. `test_phase_18_added_no_system_context_bypass` asserts `core/deps.py` and `core/auth.py` hold no call site, with comments and docstrings stripped (both files discuss the bypass at length). **Note for future readers:** `tenancy.py`'s docstring says "exactly four greppable call sites" and there are 21 literal statements — the four are *categories*, and later phases added statements within them. Do not read that docstring as a live count. Phase 18 changed it by zero either way. |
| No change to any of the 436 `CurrentUserDep` call sites | **met** | `git diff dev...HEAD -- backend/app \| grep '^-.*CurrentUserDep'` is **empty**. Total count goes 436 → 439: the three new `/api-keys` endpoints, each taking `current: CurrentUserDep`. |
| `nginx -t` passes and the limit is observed firing | **met** | Both run live in a container, not read. See "What verified it" above: syntax test successful; 22 through then `429`s; a second credential unaffected; unauthenticated unlimited. |
| `DECISIONS.md`, `docs/api.md` and `PROGRESS.md` updated | **met** | D-069 rewritten after the budget fix; D-070 added for the mint-escalation fix. `docs/api.md` §1 carries the D-070 restriction, §2–3 the UUID key format, §5 the audit limitation and the dedicated-service-user instruction, §6 the 429 contract. `docs/modules/admin.md` carries the endpoint table. The `PROGRESS.md` Phase 18 entry has been corrected — as written by the build it still claimed the slug format, `find_tenant_by_slug` per request, "exactly 3 statements", and "not AuditMixin", all three of which the review changed. |

**Contract audit — Q1's explicit "Not taken" list, checked mechanically, all honoured:**
no OAuth server / token endpoint / client registry (the branch adds exactly three routes, all
`/api-keys`); no `last_used_at` write (no such column, no `UPDATE` on the auth path, and the
exact-count test asserts every counted statement is a `SELECT`); no Python rate limiter (`pyproject.toml`
and `uv.lock` are untouched, so no dependency was added); no CORS change (`app/main.py` and
`app/core/config.py` are untouched); no change to D-007/D-009/D-010/D-011/D-013 (`core/tenancy.py`,
`core/audit.py`, `core/docflow.py` and `core/numbering.py` are untouched — `core/idempotency.py`
gains a docstring only, no schema or behaviour); no change to any of the 436 `CurrentUserDep` call
sites.

## Known limits — recorded, not fixed

Each of these would require changing something on Q1's "Not taken" list. Each is pinned by a test
that fails if the assumption behind it stops holding.

1. **The audit trail cannot tell a machine from its human.** The same user writing once by JWT and
   once by key produces two audit rows equal in `actor_user_id` and `request_ip`, and
   `core_audit_log` has no `source` column (D-010's literal schema named one; PLAN 3.5 dropped it).
   Adding one is a D-010 change. **This is the limit that changes operator behaviour:** the property
   is recoverable at zero code cost by binding the key to a *dedicated service user*, so the actor
   column names the website. `docs/api.md` §1 and §5 now instruct exactly that and state the limit
   outright. It is a convention, not an enforced property — nothing rejects a key bound to a real
   person, and one bound to a person will attribute that person's name to the website's writes.
   Pinned by `test_audit_row_cannot_distinguish_a_key_from_its_human`.

2. **An external machine principal shares the tenant's D-013 idempotency namespace.** The
   reservation PK is `(tenant_id, endpoint, key)` with no principal column, so a key and a staff
   user presenting the same `Idempotency-Key` on the same endpoint meet on one row: same body
   replays the other principal's stored response verbatim, a different body is 422, an unfinished
   one is 409. Bounded — it is same-tenant only, both principals must already hold the endpoint
   permission (`require_permission` is solved *before* the guard, so a replay never crosses the
   RBAC line), and keys are client-chosen randoms so a collision must be guessed. The genuinely
   sharp edge is that replay re-emits a stored body and skips serialization, so a D-009 `Masked`
   field in an idempotent endpoint's response *would* cross unmasked. No such endpoint exists
   today — by coincidence, not design — so a route-introspection gate test now fails the day one is
   added, and `core/idempotency.py`'s docstring says that adding one means adding a principal
   column. Pinned by `test_no_idempotent_endpoint_serializes_a_masked_field` (with positive
   controls, so the green is not vacuous).

3. **Two simultaneous revokes of one key can report two timestamps.** `revoke_api_key` is
   read-then-write, so both transactions read `revoked_at IS NULL` and both write; the later stamp
   can win and one caller is told a time that is not the stored one. Left alone deliberately: the
   credential is equally dead either way, and the only fix that closes the window is an atomic
   `UPDATE ... WHERE revoked_at IS NULL` — which, now that `ApiKey` is `AuditMixin`, is not
   available in either form. The ORM form is a hard 409 from `core/audit.py`'s
   `_guard_bulk_audited_writes`, and a raw Core UPDATE skips the flush events D-010 capture hooks.
   Trading audit coverage for milliseconds of timestamp precision is the wrong trade. The sequential
   retry an operator actually performs *does* return the first timestamp; the docstrings in
   `admin/service.py` and `admin/router.py` were corrected to claim only that. Pinned by
   `test_sequential_double_revoke_keeps_the_first_timestamp` and
   `test_simultaneous_double_revoke_is_effective_but_reports_two_timestamps`.

Two further observations, neither a defect and neither Phase 18's doing, recorded so they are not
re-litigated:

- **`token_version` is not a kill switch for API keys.** Bumping it kills the JWT and leaves the
  key alive. That is correct — `token_version` is D-008's invalidation counter for *stateless*
  tokens, and a key is a row that carries its own `revoked_at` — but the code comment claimed
  otherwise, which would have left an operator reaching for "revoke everything" believing they
  revoked more than they did. The comment is corrected and now names all three switches:
  `revoked_at` kills one credential, `expires_at` retires it on schedule, `user.is_active` /
  `tenant.is_active` kill the whole principal and every key bound to it. If a revoke-everything
  endpoint ever ships, a stamped version column on `core_api_keys` is the upgrade path and the
  comment says so.
- **`ix_core_api_keys_tenant_id` is redundant** — a strict prefix of two other indexes on a
  write-light table. It comes from `TenantMixin`'s `index=True`, which every tenant-scoped table in
  the repo carries, so changing it is a schema decision for the whole codebase rather than a review
  fix.

## Scope status

**Committed.** Hospitality is tracked in `PLAN.md` as Phases 18-20 following the owner's explicit
go-ahead on 2026-08-14, and this branch merged to `dev` as PR #188. The proposal-only fence this
file previously described was correct while it stood and was lifted by a human decision, not by
drift.
