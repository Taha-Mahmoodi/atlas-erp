"""GET /api/v1/health — app-level plumbing wired in app.main."""

from httpx import AsyncClient

from app.core.config import get_settings


async def test_health_returns_200_with_status_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] == get_settings().env


async def test_health_response_carries_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers["X-Request-ID"]
