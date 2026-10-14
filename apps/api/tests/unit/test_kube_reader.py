"""The read-only Kubernetes adapter: configuration seen per revision, never secret values."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from opspilot_api.kube import KubernetesReader, NamespaceNotAllowed, template_config

T1 = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def template() -> client.V1PodTemplateSpec:
    env = [
        client.V1EnvVar(name="SERVICE_VERSION", value="1.4.2"),
        client.V1EnvVar(name="DB_PASSWORD", value="hunter-two"),
        client.V1EnvVar(
            name="API_TOKEN",
            value_from=client.V1EnvVarSource(
                secret_key_ref=client.V1SecretKeySelector(name="payment-provider", key="token")
            ),
        ),
        client.V1EnvVar(
            name="LOG_LEVEL",
            value_from=client.V1EnvVarSource(
                config_map_key_ref=client.V1ConfigMapKeySelector(name="shop", key="log-level")
            ),
        ),
        client.V1EnvVar(
            name="POD_NAME",
            value_from=client.V1EnvVarSource(
                field_ref=client.V1ObjectFieldSelector(field_path="metadata.name")
            ),
        ),
    ]
    container = client.V1Container(
        name="checkout",
        env=env,
        env_from=[client.V1EnvFromSource(secret_ref=client.V1SecretEnvSource(name="db"))],
    )
    volumes = [
        client.V1Volume(name="c", config_map=client.V1ConfigMapVolumeSource(name="flags")),
        client.V1Volume(name="s", secret=client.V1SecretVolumeSource(secret_name="tls")),
    ]
    return client.V1PodTemplateSpec(spec=client.V1PodSpec(containers=[container], volumes=volumes))


def test_template_config_names_references_and_never_carries_secret_values() -> None:
    env, refs = template_config(template())

    assert env == {
        "SERVICE_VERSION": "1.4.2",
        "DB_PASSWORD": "[REDACTED]",
        "API_TOKEN": "[REDACTED]",
        "LOG_LEVEL": "<from configmap shop key log-level>",
        "POD_NAME": "<from the pod or its resources>",
    }
    assert refs == (
        "configmap/flags",
        "configmap/shop",
        "secret/db",
        "secret/payment-provider",
        "secret/tls",
    )
    assert "hunter-two" not in repr(env)


def reader(core: MagicMock) -> KubernetesReader:
    r = KubernetesReader(frozenset({"demo"}))
    r._apps = MagicMock()
    return r


async def test_config_maps_return_metadata_and_key_names_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = MagicMock()
    core.read_namespaced_config_map.side_effect = [
        client.V1ConfigMap(
            metadata=client.V1ObjectMeta(
                name="shop",
                creation_timestamp=T1,
                managed_fields=[
                    client.V1ManagedFieldsEntry(time=T1),
                    client.V1ManagedFieldsEntry(time=T2),
                ],
            ),
            data={"log-level": "debug", "feature": "on"},
        ),
        ApiException(status=404),
    ]
    monkeypatch.setattr(client, "CoreV1Api", lambda api_client: core)
    r = reader(core)

    found = await r.config_maps("demo", ["shop", "gone"])

    assert [(c.name, c.updated_at, c.keys) for c in found] == [
        ("shop", T2, ("feature", "log-level"))
    ]
    assert [c.args for c in core.read_namespaced_config_map.call_args_list] == [
        ("shop", "demo"),
        ("gone", "demo"),
    ]
    core.read_namespaced_secret.assert_not_called()


async def test_config_maps_outside_allowed_namespaces_are_refused_without_api_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = MagicMock()
    monkeypatch.setattr(client, "CoreV1Api", lambda api_client: core)
    r = reader(core)

    with pytest.raises(NamespaceNotAllowed):
        await r.config_maps("kube-system", ["coredns"])

    core.read_namespaced_config_map.assert_not_called()
