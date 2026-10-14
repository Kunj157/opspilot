"""KubernetesWriter against a mocked client API: the exact calls and patch bodies it sends."""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from opspilot_api.kube import KubernetesWriter, NamespaceNotAllowed, RemediationFailed


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


def replica_set(owner_uid: str, revision: int, image: str, version: str) -> client.V1ReplicaSet:
    return client.V1ReplicaSet(
        metadata=client.V1ObjectMeta(
            owner_references=[
                client.V1OwnerReference(
                    api_version="apps/v1", kind="Deployment", name="checkout", uid=owner_uid
                )
            ],
            annotations={"deployment.kubernetes.io/revision": str(revision)},
        ),
        spec=client.V1ReplicaSetSpec(
            selector=client.V1LabelSelector(match_labels={"app": "checkout"}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": "checkout", "pod-template-hash": f"h{revision}"}
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="checkout",
                            image=image,
                            env=[client.V1EnvVar(name="SERVICE_VERSION", value=version)],
                        )
                    ]
                ),
            ),
        ),
    )


@pytest.fixture
def history(apps: MagicMock) -> MagicMock:
    apps.read_namespaced_deployment.return_value = MagicMock(**{"metadata.uid": "deploy-uid"})
    apps.list_namespaced_replica_set.return_value = client.V1ReplicaSetList(
        items=[
            replica_set("deploy-uid", 18, "shop:1.0.0", "1.0.0"),
            replica_set("deploy-uid", 19, "shop:1.4.2", "1.4.2"),
            replica_set("other-uid", 18, "other:9", "9"),
        ]
    )
    apps.api_client = client.ApiClient()
    return apps


async def test_rollback_replaces_the_template_with_the_target_revision(
    writer: KubernetesWriter, history: MagicMock
) -> None:
    result = await writer.rollback_deployment("demo", "checkout", 18, cause="OpsPilot rollback")

    history.read_namespaced_deployment.assert_called_once_with("checkout", "demo")
    history.list_namespaced_replica_set.assert_called_once_with("demo")
    [call] = history.patch_namespaced_deployment.call_args_list
    name, namespace, body = call.args
    assert (name, namespace) == ("checkout", "demo")
    assert body == [
        {
            "op": "replace",
            "path": "/spec/template",
            "value": {
                # The pod-template-hash label is dropped, as `kubectl rollout undo` does.
                "metadata": {"labels": {"app": "checkout"}},
                "spec": {
                    "containers": [
                        {
                            "name": "checkout",
                            "image": "shop:1.0.0",
                            "env": [{"name": "SERVICE_VERSION", "value": "1.0.0"}],
                        }
                    ]
                },
            },
        },
        {
            "op": "add",
            "path": "/metadata/annotations/kubernetes.io~1change-cause",
            "value": "OpsPilot rollback",
        },
    ]
    assert result == {"rolled_back_to": 18, "version": "1.0.0", "image": "shop:1.0.0"}


async def test_rollback_to_a_revision_that_no_longer_exists_patches_nothing(
    writer: KubernetesWriter, history: MagicMock
) -> None:
    with pytest.raises(RemediationFailed, match="revision 7 of checkout no longer exists"):
        await writer.rollback_deployment("demo", "checkout", 7, cause="x")

    history.patch_namespaced_deployment.assert_not_called()


async def test_restart_patches_only_the_restarted_at_annotation(
    writer: KubernetesWriter, apps: MagicMock
) -> None:
    result = await writer.restart_deployment(
        "demo", "checkout", restarted_at="2026-10-14T10:00:00+00:00"
    )

    apps.patch_namespaced_deployment.assert_called_once_with(
        "checkout",
        "demo",
        {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": "2026-10-14T10:00:00+00:00"
                        }
                    }
                }
            }
        },
    )
    assert result == {"restarted_at": "2026-10-14T10:00:00+00:00"}


async def test_scale_reads_the_current_replicas_then_patches_the_scale(
    writer: KubernetesWriter, apps: MagicMock
) -> None:
    apps.read_namespaced_deployment_scale.return_value = client.V1Scale(
        spec=client.V1ScaleSpec(replicas=2)
    )

    result = await writer.scale_deployment_within_bounds("demo", "checkout", 4, maximum=6)

    apps.read_namespaced_deployment_scale.assert_called_once_with("checkout", "demo")
    apps.patch_namespaced_deployment_scale.assert_called_once_with(
        "checkout", "demo", {"spec": {"replicas": 4}}
    )
    assert result == {"replicas_before": 2, "replicas": 4}


@pytest.mark.parametrize("replicas", [0, 7, -1])
async def test_scaling_outside_the_bounds_makes_no_api_call(
    writer: KubernetesWriter, apps: MagicMock, replicas: int
) -> None:
    with pytest.raises(RemediationFailed, match=r"outside 1\.\.6"):
        await writer.scale_deployment_within_bounds("demo", "checkout", replicas, maximum=6)

    assert apps.mock_calls == []


@pytest.mark.parametrize(
    "action",
    [
        lambda w: w.rollback_deployment("kube-system", "coredns", 3, cause="x"),
        lambda w: w.restart_deployment("kube-system", "coredns", restarted_at="t"),
        lambda w: w.scale_deployment_within_bounds("default", "web", 2, maximum=6),
        lambda w: w.pause_rollout("opspilot", "api"),
    ],
    ids=["rollback", "restart", "scale", "pause"],
)
async def test_no_action_reaches_the_api_outside_the_allowed_namespaces(
    writer: KubernetesWriter, apps: MagicMock, action: Callable[[KubernetesWriter], Awaitable[Any]]
) -> None:
    with pytest.raises(NamespaceNotAllowed):
        await action(writer)

    assert apps.mock_calls == []


async def test_api_errors_become_remediation_failures(
    writer: KubernetesWriter, apps: MagicMock
) -> None:
    apps.patch_namespaced_deployment.side_effect = ApiException(status=403, reason="Forbidden")

    with pytest.raises(RemediationFailed, match="Kubernetes API error 403: Forbidden"):
        await writer.pause_rollout("demo", "checkout")
