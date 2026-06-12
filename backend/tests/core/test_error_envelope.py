"""Every non-2xx renders the D-014 error envelope {error: {code, message, details,
request_id}} — including FastAPI's own HTTPException and validation errors.

Test-only routes are added to a local create_app() instance so production app.main
stays free of test endpoints."""

from httpx import ASGITransport, AsyncClient

from app.core.exceptions import ConflictError
from app.main import create_app


async def test_unknown_path_returns_404_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "common.not_found"
    assert error["message"]
    assert error["request_id"]


async def test_atlas_error_renders_envelope_with_request_id() -> None:
    app = create_app()

    @app.get("/api/v1/test/conflict")
    async def raise_conflict() -> None:
        raise ConflictError("Duplicate document number", details={"doc_no": "JE-001"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/test/conflict")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "common.conflict"
    assert error["message"] == "Duplicate document number"
    assert error["details"] == {"doc_no": "JE-001"}
    assert error["request_id"]
    assert response.headers["X-Request-ID"] == error["request_id"]


async def test_validation_error_returns_422_envelope() -> None:
    app = create_app()

    @app.get("/api/v1/test/echo")
    async def echo(limit: int) -> dict[str, int]:
        return {"limit": limit}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/test/echo", params={"limit": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "common.validation_error"
    assert isinstance(error["details"], list)
    first = error["details"][0]
    assert first["field"] == "query.limit"
    assert first["message"]
    assert first["type"]
    assert error["request_id"]
