# Phase 18 (machine credential) — build status

**Written when the build was stopped on request, 2026-08-14. Read this before touching the
`feat/core-api-key-credential` branch.**

## The one thing that matters

**This branch is UNVERIFIED and must not be merged as it stands.** All six plan tasks were
implemented and committed, but the adversarial review and the final verification gate never ran —
the build was stopped after the build phase. Nothing here has been security-reviewed, and the full
test suite has not been run against the finished branch.

## What exists

Branch: `feat/core-api-key-credential`, cut from `dev` at `a9967da`. Six commits, one per plan task:

| Commit | Task | What it does |
|---|---|---|
| `10e109d` | T1 | `ApiKey` model + Alembic migration |
| `f62fc1e` | T2 | `mint_api_key` / `parse_api_key` in `core/auth.py` |
| `e69017c` | T3 | The API-key branch inside `get_current_user` |
| `cd41423` | T4 | Admin endpoints: create, list, revoke |
| `f3a1756` | T5 | nginx `limit_req` on `/api`, keyed on the Authorization header |
| `59f8808` | T6 | D-069, `docs/api.md` operator flow, admin module guide, PROGRESS entry |

The plan it was built from: [`hospitality-build-plan.md`](./hospitality-build-plan.md), Phase 18.
The spec that plan argues from: [`hospitality-industry-plan.md`](./hospitality-industry-plan.md), Q1.

## What was verified, and what was not

**Verified** — each task agent ran its own targeted tests TDD-style (failing test first, then
implementation, then green) before committing. Those tests are in the branch.

**NOT verified — all of it still owed:**

1. **The full backend suite has not been run against the finished branch.** Baseline before this
   phase is **1786 passed, 20 skipped**. Task agents were explicitly told to run only targeted
   tests, because the suite takes 5+ minutes and a later phase was supposed to run it. That phase
   never ran.
2. **`ruff check` has not been run.**
3. **No adversarial security review happened.** Four attackers were designed and never dispatched:
   - **tenant isolation** — forged tenant refs, a key whose `user_id` belongs to another tenant,
     stale ContextVars, and whether the ordinary D-007 filter (not a hand-written where-clause) is
     what stops each case
   - **scope containment** — scopes naming a permission the user lacks, `scopes: []` vs
     `scopes: null`, uncatalogued keys, and whether the 60-second `resolve_permissions`
     memoization keeps a revoked key alive
   - **lifecycle** — revocation, expiry, deactivated user, the `token_version` kill-switch,
     double-revoke, cross-tenant revoke, and whether the list endpoint can leak `secret_sha256`
   - **budget and contract** — is the lookup really one joined query, and was anything on Q1's
     explicit "not taken" list quietly taken
4. **A second wave of attackers was identified but never written.** These cover gaps the first four
   do not, and at least the first is a real risk the spec called out by name:
   - **audit-actor resolution** — Q1 warns that binding a key to a real `core_users` row is what
     keeps `AuditLog.actor_user_id` resolvable across the 13 `submitted_by`/`approver_id` sites
     that deliberately do not FK to `core_users`. **Nothing tests this.**
   - **migration reversibility** — does `downgrade` work, on both PostgreSQL and SQLite (D-003)?
   - **key-format parsing** — `parse_api_key` splits on `_` with `maxsplit=2`; a tenant slug
     containing an underscore is the obvious case, plus unicode, empty segments, very long input
   - **concurrency** — duplicate secret on mint (the unique constraint), and revoke racing an
     in-flight authentication
5. **The plan's own "Phase 18 done when" checklist was never walked.**

## The known concern, recorded honestly by the build itself

D-069 states that an API-key-authenticated list request spends **exactly 3 statements** (slug
resolve + auth join + page). That passes PERFORMANCE §2's ≤3 — **with no margin left.**

This matters because `backend/tests/conftest.py:140,160-163` is explicit that the budget's one
query of slack is a *regression margin, not headroom*, and the plan repeated that warning. The
implementation spent it on resolving the tenant slug. D-069 names the escape hatch — mint the key
on the tenant UUID rather than the slug, removing the resolve — and correctly rules out raising the
budget. **This should be settled before merge, not after**, because it means any future query added
to an API-key request path immediately breaches the budget.

## To resume

1. Run the full suite and `ruff check .` against the branch. Fix whatever is red.
2. Dispatch the four original attackers, then the four second-wave ones above. They fix what they
   break and commit their tests either way — the tests are the regression net.
3. Settle the query-budget question (slug vs UUID in the key).
4. Walk the plan's done-checklist item by item, ticking only what is actually verified.
5. Only then open a PR to `dev`.

The workflow that built this is resumable — the script is at
`~/.claude/projects/-Users-taha-Documents-atlas-erp/.../workflows/scripts/phase-18-api-credential-wf_9ba4dbc9-1fd.js`
and completed agents replay from cache with
`Workflow({scriptPath: ..., resumeFromRunId: 'wf_9ba4dbc9-1fd'})`.

## Scope fence — still intact

`PLAN.md`, `STRUCTURE.md` and `GITHUB-WORKFLOW.md` are untouched. Hospitality is still a proposal;
this branch is an unmerged spike against a reviewed plan, not committed scope. Promoting it is a
separate, explicit decision.
