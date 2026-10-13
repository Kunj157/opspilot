import httpx

from opspilot_demo.loadgen import LoadSettings, run


async def test_sends_a_browse_and_checkout_mix_at_the_requested_rate() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json={"status": "ok"})

    settings = LoadSettings(target_url="http://storefront", rps=50, checkout_ratio=0.25)
    stats = await run(settings, requests=40, transport=httpx.MockTransport(handler), seed=7)

    assert stats.sent == 40
    assert stats.failed == 0
    assert set(seen) == {"GET /api/products", "POST /api/checkout"}
    assert 4 <= seen.count("POST /api/checkout") <= 16


async def test_counts_failures_and_keeps_going() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    stats = await run(
        LoadSettings(target_url="http://storefront", rps=100),
        requests=10,
        transport=httpx.MockTransport(handler),
    )

    assert (stats.sent, stats.failed) == (10, 10)
