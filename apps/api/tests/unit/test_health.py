import httpx


async def test_health_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_does_not_touch_dependencies(client: httpx.AsyncClient) -> None:
    # The fixture points at unreachable hosts; liveness must still pass.
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
