"""Response compression (PERFORMANCE §3): GZipMiddleware wired in app.main.

Large bodies are gzipped when the client accepts it; tiny bodies pass through uncompressed
(minimum_size=500); the RequestIdMiddleware header survives compression (closes the
middleware-ordering question for #27's gzip half).
"""

from httpx import AsyncClient


async def test_large_response_is_gzipped(client: AsyncClient) -> None:
    # The OpenAPI document is far above minimum_size and needs no auth.
    response = await client.get(
        "/api/v1/openapi.json", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status_code == 200
    assert response.headers["Content-Encoding"] == "gzip"
    # httpx transparently decompresses; the body is still valid JSON.
    assert response.json()["info"]["title"] == "Atlas ERP"


async def test_tiny_response_stays_uncompressed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "Content-Encoding" not in response.headers


async def test_gzipped_response_keeps_request_id_header(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/openapi.json", headers={"Accept-Encoding": "gzip"}
    )
    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers["X-Request-ID"]
