# Atlas ERP — developer entry points. Frontend targets arrive with Phase 15.

.PHONY: backend-install lint test dev up down migrate

backend-install:
	cd backend && uv sync

lint:
	cd backend && uv run ruff check .

test:
	cd backend && uv run pytest -q

dev:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head
