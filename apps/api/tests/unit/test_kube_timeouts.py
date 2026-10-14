"""Every Kubernetes API call carries a request timeout (a silent API server must not hang us)."""

from typing import Any

from opspilot_api.kube import _Timed


class FakeApi:
    api_client = object()

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def patch_namespaced_deployment(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        return "patched"


def test_calls_get_the_request_timeout() -> None:
    api = FakeApi()
    timed = _Timed(api, 7.5)

    assert timed.patch_namespaced_deployment("checkout", "demo", {}) == "patched"
    assert api.calls == [(("checkout", "demo", {}), {"_request_timeout": 7.5})]
    assert timed.api_client is api.api_client


def test_an_explicit_timeout_wins() -> None:
    api = FakeApi()

    _Timed(api, 7.5).patch_namespaced_deployment("x", "demo", {}, _request_timeout=1)

    assert api.calls[0][1] == {"_request_timeout": 1}
