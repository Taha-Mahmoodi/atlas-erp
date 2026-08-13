# Build context is the REPO ROOT (see docker-compose.yml): the image must also ship
# /industry-templates, which the industry loader resolves relative to the repo root
# (loader.py parents[4] — /app/app/... puts the "repo root" at /).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependency layer first so code edits do not invalidate the dependency cache.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/seed.py ./
COPY industry-templates /industry-templates
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
