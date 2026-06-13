# Atlas ERP — developer entry points. Frontend targets arrive with Phase 15.

.PHONY: backend-install lint test test-pg perf dev up down migrate

backend-install:
	cd backend && uv sync

lint:
	cd backend && uv run ruff check .

test:
	cd backend && uv run pytest -q -m "not pg and not perf"

# Runs the PostgreSQL-only guard subset; ATLAS_DATABASE_URL must point at a real
# Postgres (the financial DB triggers and UPDATE...RETURNING can't be proven on SQLite).
test-pg:
	cd backend && uv run pytest -q -m pg

# PERFORMANCE §5 perf smoke (PLAN 4P.7): SQLite at 2x budgets by default; point
# ATLAS_PERF_DATABASE_URL at a real Postgres to assert the 1x budgets before a promotion.
perf:
	cd backend && uv run pytest -q -m perf -s

dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head
