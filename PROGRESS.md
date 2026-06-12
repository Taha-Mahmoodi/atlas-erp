# PROGRESS.md — Build Log

One line per completed task, newest at the bottom. This file is the single source of truth for "where was I" — verify the last entry against `git log` before resuming work.

- [done] 0.1 Public repo `Taha-Mahmoodi/atlas-erp` created; `.gitignore` is the root commit on `main` (44369b8)
- [done] 0.2 `dev` branch created and pushed; feature-branch flow active from here on
- [done] 0.3 16 labels created (module:*, severity:*, bug, enhancement, tech-debt, found-during-build)
- [done] 0.4 State files written: CLAUDE.md, PLAN.md, PROGRESS.md, DECISIONS.md + STRUCTURE.md/GITHUB-WORKFLOW.md copied to root
- [done] 0.5 Governance docs: LICENSE (Apache-2.0), NOTICE, README, CONTRIBUTING.md, SECURITY.md, .env.example
- [done] 0.6 CI (`backend`+`frontend` jobs, guarded green pre-code) + PR template + bug/feature issue forms
- [done] 0.7 PR #1 squash-merged to `dev`; branch protection live on `main`+`dev` (required checks backend+frontend, enforce_admins, no force-push)
- [done] 1.1 12 parallel research agents covered all S/4HANA areas from live web sources (June 2026)
- [done] 1.2 docs/research/s4hana-parity.md: 139 capabilities mapped — 45 full / 48 partial / 46 out-of-scope, every cut with reason + later path
- [done] 2.1 PLAN.md expanded: 50 tasks across Phases 3–17, one task = one PR, promotion milestones fixed
- [done] 2.2 Architect panel (2 domain architects + adversarial consolidator) → 20 decisions D-007..D-026 in DECISIONS.md, full spec in docs/architecture.md (643 lines)
- [done] 2.3 STRUCTURE.md amended per D-011/D-015/D-016 (core/money.py, core/custom_fields.py, events.py import allowance); no other tree changes
- [done] 3.1 Backend scaffold: uv project, app factory + error envelope + request-id middleware, build_engine with SQLite FK pragma, Base + naming convention, async Alembic (0001 baseline), template-copy test harness, Makefile + docker-compose — 7 tests green
- [done] 3.2 Tenancy (D-007): core/tenancy.py do_orm_execute fail-closed filter + before_flush stamping + system_context; TenantMixin/UuidPKMixin/tenant_fk in models; adm_tenants + adm_tenant_settings (migration 0002); 18 tenancy tests incl. mapper-enumeration auto-cover + FK backstop + grep gate — 25 tests green total
- [done] 3.3 Auth (D-008): core/auth.py (argon2id off-thread + HS256 JWT), core_users + core_refresh_sessions (migration 0003), CAS refresh rotation with 10s grace + family revocation, get_current_user sets production tenant ContextVar, middleware resets it; +20 tests (51 total). D-027 records core auth-table/router placement.
