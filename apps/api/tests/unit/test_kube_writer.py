"""KubernetesWriter against a mocked client API: the exact calls and patch bodies it sends."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from opspilot_api.kube import KubernetesWriter, NamespaceNotAllowed


@pytest.fixture
def apps() -> MagicMock:
    return MagicMock(name="AppsV1Api")


@pytest.fixture
def writer(apps: MagicMock) -> KubernetesWriter:
    writer = KubernetesWriter(frozenset({"demo"}))
    writer._apps = apps  # The client is built lazily; tests hand it a mock instead.
    return writer


async def test_pause_sets_spec_paused_and_nothing_else(
    writer: KubernetesWriter, apps: MagicMock
) -> None:
    result: dict[str, Any] = await writer.pause_rollout("demo", "checkout")

    apps.patch_namespaced_deployment.assert_called_once_with(
        "checkout", "demo", {"spec": {"paused": True}}
    )
    assert result == {"paused": True}


async def test_pausing_outside_the_allowed_namespaces_makes_no_api_call(
    writer: KubernetesWriter, apps: MagicMock
) -> None:
    with pytest.raises(NamespaceNotAllowed):
        await writer.pause_rollout("kube-system", "coredns")

    assert apps.mock_calls == []
