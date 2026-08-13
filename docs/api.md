# API Reference

The API reference is the OpenAPI spec the backend generates from its Pydantic schemas — it is never written by hand and never drifts from the code.

- **Interactive docs (Swagger UI):** `http://localhost:8000/api/v1/docs`
- **Raw spec:** `http://localhost:8000/api/v1/openapi.json`

Run the stack per the README quickstart (`docker-compose up`), then open either URL. Every endpoint lives under the versioned prefix `/api/v1`.

Conventions that apply across all endpoints — cursor pagination, the error envelope with machine codes, `Idempotency-Key` on financial/stock document creation, tenancy and auth headers — are specified in [architecture.md](architecture.md). Per-module behavior is documented in [`docs/modules/`](modules/).
