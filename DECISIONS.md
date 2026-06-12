# DECISIONS.md — Design Decision Log

One line per consequential decision + rationale, so later sessions don't re-litigate or contradict earlier choices. Numbered, append-only; superseding a decision gets a new entry referencing the old one.

- **D-001 Bootstrap exception to "nothing directly on main":** the `.gitignore` root commit lands directly on `main` (GITHUB-WORKFLOW.md §1 explicitly orders it first); everything else reaches `main` only via `dev` promotions. Rationale: a branch cannot be cut from an empty repo.
- **D-002 Python toolchain = uv + Python 3.12:** uv manages the venv, lockfile (`uv.lock`, committed) and Python pin; CI uses `astral-sh/setup-uv`. Rationale: fastest reproducible installs, single tool for venv+lock+run.
- **D-003 Tests on SQLite (aiosqlite), runtime on PostgreSQL:** models are written PostgreSQL-first with SQLite-compatible type fallbacks (e.g. JSON variant for JSONB, Numeric for money); the full suite and CI run against in-memory/file SQLite, while docker-compose runs Postgres. Rationale: the prompt requires PostgreSQL-first + SQLite-compatible demo; SQLite keeps CI fast and dependency-free. DB-level financial constraints must be expressed portably (CHECK constraints, not Postgres-only features) or get Postgres-only guards documented per case.
- **D-004 Frontend package manager = npm:** lockfile committed; no pnpm/yarn. Rationale: zero extra tooling on contributor machines.
- **D-005 CI check names are stable from PR #1:** single workflow `ci.yml` with jobs `backend` and `frontend`; each job no-ops green while its directory doesn't exist yet. Rationale: branch protection requires named status checks; names must exist before the code does.
- **D-006 Makefile and docker-compose.yml are deferred to the first backend PR:** a Makefile whose targets point at directories that don't exist would violate the no-orphan-files rule in spirit. Rationale: every committed file must work the day it lands.
