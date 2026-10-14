"""Kubernetes access, limited to allow-listed namespaces.

Investigations get a reader with three questions: a deployment's rollout
history (with each revision's configuration), its current rollout status,
and metadata of the ConfigMaps it uses. Secrets are never read: they are
only named, as the pod template references them. Approved remediations get a writer
with three actions: roll back to a revision, restart, and scale within
bounds. There is no generic API access.
"""

import asyncio
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol

from opspilot_api.redaction import redact


class NamespaceNotAllowed(Exception):
    """The namespace is outside the investigation allow-list."""


@dataclass(frozen=True)
class Revision:
    revision: int
    created_at: datetime | None
    change_cause: str | None
    version: str | None
    image: str | None
    # Environment of the first container, values redacted; references shown as "<from ...>".
    env: dict[str, str] = field(default_factory=dict)
    # ConfigMaps and Secrets the pod template uses, e.g. "configmap/shop", "secret/db".
    config_refs: tuple[str, ...] = ()
    # Source commit from pod template annotations: sha, author, message, pull_request, source.
    commit: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigMapInfo:
    """Metadata only: when it last changed and which keys it has, never the values."""

    name: str
    updated_at: datetime | None
    keys: tuple[str, ...]


@dataclass(frozen=True)
class RolloutStatus:
    desired: int
    updated: int
    ready: int
    available: int
    complete: bool
    conditions: list[str]


class KubeReader(Protocol):
    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]: ...

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus: ...

    async def config_maps(self, namespace: str, names: list[str]) -> list[ConfigMapInfo]: ...


def check_namespace(namespace: str, allowed: frozenset[str]) -> None:
    if namespace not in allowed:
        raise NamespaceNotAllowed(f"namespace {namespace!r} is not allowed")


def _env(container: Any, name: str) -> str | None:
    for env in container.env or []:
        if env.name == name:
            value: str | None = env.value
            return value
    return None


MAX_ENV_VALUE = 120


def _env_value(env: Any) -> str:
    source = env.value_from
    if source is None:
        return str(env.value or "")[:MAX_ENV_VALUE]
    if source.secret_key_ref is not None:
        return f"<from secret {source.secret_key_ref.name}>"
    if source.config_map_key_ref is not None:
        ref = source.config_map_key_ref
        return f"<from configmap {ref.name} key {ref.key}>"
    return "<from the pod or its resources>"


def template_config(template: Any) -> tuple[dict[str, str], tuple[str, ...]]:
    """(redacted environment of the first container, ConfigMap/Secret references)."""
    spec = template.spec
    container = spec.containers[0]
    env = {e.name: _env_value(e) for e in container.env or []}
    refs: set[str] = set()
    for c in spec.containers:
        for e in c.env or []:
            if e.value_from is not None and e.value_from.secret_key_ref is not None:
                refs.add(f"secret/{e.value_from.secret_key_ref.name}")
            if e.value_from is not None and e.value_from.config_map_key_ref is not None:
                refs.add(f"configmap/{e.value_from.config_map_key_ref.name}")
        for source in c.env_from or []:
            if source.config_map_ref is not None:
                refs.add(f"configmap/{source.config_map_ref.name}")
            if source.secret_ref is not None:
                refs.add(f"secret/{source.secret_ref.name}")
    for volume in spec.volumes or []:
        if volume.config_map is not None:
            refs.add(f"configmap/{volume.config_map.name}")
        if volume.secret is not None:
            refs.add(f"secret/{volume.secret.secret_name}")
    return redact(env), tuple(sorted(refs))


# Pod template annotation → commit field; the first one present wins.
COMMIT_ANNOTATIONS = {
    "sha": ("opspilot.io/commit-sha", "org.opencontainers.image.revision"),
    "author": ("opspilot.io/commit-author",),
    "message": ("opspilot.io/commit-message",),
    "pull_request": ("opspilot.io/pull-request",),
    "source": ("opspilot.io/source", "org.opencontainers.image.source"),
}
MAX_COMMIT_MESSAGE = 200


def template_commit(annotations: dict[str, str] | None) -> dict[str, str]:
    """The commit a revision was built from; e-mail addresses are dropped."""
    commit: dict[str, str] = {}
    for key, names in COMMIT_ANNOTATIONS.items():
        value = next((v for n in names if (v := (annotations or {}).get(n, "").strip())), "")
        if key == "author":
            value = re.sub(r"\s*<[^>]*>|\S+@\S+", "", value).strip()
        if value:
            commit[key] = value[:MAX_COMMIT_MESSAGE] if key == "message" else value[:300]
    return commit


class KubernetesReader:
    """The official client, run in a thread; config is loaded on first use."""

    def __init__(
        self,
        allowed_namespaces: frozenset[str],
        *,
        context: str | None = None,
        config_file: str | None = None,
    ) -> None:
        self.allowed = allowed_namespaces
        self.context = context
        self.config_file = config_file
        self._apps: Any = None

    def _api(self) -> Any:
        if self._apps is None:
            from kubernetes import client, config  # Imported lazily: the API never needs it.

            try:
                api_client = config.new_client_from_config(  # type: ignore[no-untyped-call]
                    config_file=self.config_file, context=self.context
                )
            except config.ConfigException:
                config.load_incluster_config()  # type: ignore[no-untyped-call]
                api_client = client.ApiClient()
            self._apps = client.AppsV1Api(api_client)
        return self._apps

    def _history(self, namespace: str, deployment: str) -> list[Revision]:
        apps = self._api()
        owner = apps.read_namespaced_deployment(deployment, namespace)
        replica_sets = apps.list_namespaced_replica_set(namespace).items
        revisions = []
        for rs in replica_sets:
            if not any(ref.uid == owner.metadata.uid for ref in rs.metadata.owner_references or []):
                continue
            annotations = rs.metadata.annotations or {}
            container = rs.spec.template.spec.containers[0]
            env, refs = template_config(rs.spec.template)
            revisions.append(
                Revision(
                    revision=int(annotations.get("deployment.kubernetes.io/revision", 0)),
                    created_at=rs.metadata.creation_timestamp,
                    change_cause=annotations.get("kubernetes.io/change-cause"),
                    version=_env(container, "SERVICE_VERSION"),
                    image=container.image,
                    env=env,
                    config_refs=refs,
                    commit=template_commit(
                        rs.spec.template.metadata.annotations if rs.spec.template.metadata else None
                    ),
                )
            )
        revisions.sort(key=lambda r: r.revision, reverse=True)
        if revisions:
            # A ReplicaSet reused by a rollback keeps its old creation time; its
            # current pods were created when the latest revision started rolling out.
            started = self._pods_started(namespace, owner, revisions[0].revision)
            latest = revisions[0]
            if started is not None:
                revisions[0] = replace(latest, created_at=started)
        return revisions

    def _pods_started(self, namespace: str, deployment: Any, revision: int) -> datetime | None:
        from kubernetes import client

        core = client.CoreV1Api(self._api().api_client)
        labels = deployment.spec.selector.match_labels or {}
        selector = ",".join(f"{k}={v}" for k, v in labels.items())
        apps = self._api()
        replica_sets = {
            rs.metadata.uid
            for rs in apps.list_namespaced_replica_set(namespace, label_selector=selector).items
            if (rs.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
            == str(revision)
        }
        times: list[datetime] = []
        for pod in core.list_namespaced_pod(namespace, label_selector=selector).items:
            meta = pod.metadata
            if meta is None or meta.creation_timestamp is None:
                continue
            if any(ref.uid in replica_sets for ref in meta.owner_references or []):
                times.append(meta.creation_timestamp)
        return min(times) if times else None

    def _status(self, namespace: str, deployment: str) -> RolloutStatus:
        d = self._api().read_namespaced_deployment_status(deployment, namespace)
        desired = d.spec.replicas or 0
        status = d.status
        updated, ready, available = (
            status.updated_replicas or 0,
            status.ready_replicas or 0,
            status.available_replicas or 0,
        )
        return RolloutStatus(
            desired=desired,
            updated=updated,
            ready=ready,
            available=available,
            complete=(status.observed_generation or 0) >= d.metadata.generation
            and updated == desired
            and available == desired,
            conditions=[
                f"{c.type}={c.status}" + (f" ({c.reason})" if c.reason else "")
                for c in status.conditions or []
            ],
        )

    def _config_maps(self, namespace: str, names: list[str]) -> list[ConfigMapInfo]:
        from kubernetes import client
        from kubernetes.client.exceptions import ApiException

        core = client.CoreV1Api(self._api().api_client)
        found = []
        for name in names:
            try:
                cm = core.read_namespaced_config_map(name, namespace)
            except ApiException as exc:
                if exc.status == 404:
                    continue
                raise
            meta = cm.metadata or client.V1ObjectMeta()
            times = [f.time for f in meta.managed_fields or [] if f.time is not None]
            found.append(
                ConfigMapInfo(
                    name=name,
                    updated_at=max(times) if times else meta.creation_timestamp,
                    keys=tuple(sorted({*(cm.data or {}), *(cm.binary_data or {})})),
                )
            )
        return found

    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
        check_namespace(namespace, self.allowed)
        return await asyncio.to_thread(self._history, namespace, deployment)

    async def config_maps(self, namespace: str, names: list[str]) -> list[ConfigMapInfo]:
        check_namespace(namespace, self.allowed)
        return await asyncio.to_thread(self._config_maps, namespace, names)

    async def rollout_status(self, namespace: str, deployment: str) -> RolloutStatus:
        check_namespace(namespace, self.allowed)
        return await asyncio.to_thread(self._status, namespace, deployment)


class RemediationFailed(Exception):
    """The action could not be carried out; the message says why."""


class KubeWriter(Protocol):
    async def rollback_deployment(
        self, namespace: str, deployment: str, to_revision: int, *, cause: str
    ) -> dict[str, Any]: ...

    async def restart_deployment(
        self, namespace: str, deployment: str, *, restarted_at: str
    ) -> dict[str, Any]: ...

    async def scale_deployment_within_bounds(
        self, namespace: str, deployment: str, replicas: int, *, maximum: int
    ) -> dict[str, Any]: ...


class KubernetesWriter(KubernetesReader):
    """The safe write actions. Each is idempotent for the same arguments, so a retry is harmless."""

    def _rollback(
        self, namespace: str, deployment: str, to_revision: int, cause: str
    ) -> dict[str, Any]:
        apps = self._api()
        owner = apps.read_namespaced_deployment(deployment, namespace)
        target = None
        for rs in apps.list_namespaced_replica_set(namespace).items:
            owned = any(ref.uid == owner.metadata.uid for ref in rs.metadata.owner_references or [])
            revision = (rs.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
            if owned and revision == str(to_revision):
                target = rs
        if target is None:
            raise RemediationFailed(f"revision {to_revision} of {deployment} no longer exists")
        template = apps.api_client.sanitize_for_serialization(target.spec.template)
        template.get("metadata", {}).get("labels", {}).pop("pod-template-hash", None)
        # Replace the whole template, as `kubectl rollout undo` does: a merge patch
        # would keep settings the faulty release added.
        apps.patch_namespaced_deployment(
            deployment,
            namespace,
            [
                {"op": "replace", "path": "/spec/template", "value": template},
                {
                    "op": "add",
                    "path": "/metadata/annotations/kubernetes.io~1change-cause",
                    "value": cause,
                },
            ],
        )
        container = target.spec.template.spec.containers[0]
        return {
            "rolled_back_to": to_revision,
            "version": _env(container, "SERVICE_VERSION"),
            "image": container.image,
        }

    def _restart(self, namespace: str, deployment: str, restarted_at: str) -> dict[str, Any]:
        self._api().patch_namespaced_deployment(
            deployment,
            namespace,
            {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {"kubectl.kubernetes.io/restartedAt": restarted_at}
                        }
                    }
                }
            },
        )
        return {"restarted_at": restarted_at}

    def _scale(self, namespace: str, deployment: str, replicas: int) -> dict[str, Any]:
        apps = self._api()
        before = apps.read_namespaced_deployment_scale(deployment, namespace).spec.replicas
        apps.patch_namespaced_deployment_scale(
            deployment, namespace, {"spec": {"replicas": replicas}}
        )
        return {"replicas_before": before, "replicas": replicas}

    async def _run(self, namespace: str, action: Any, *args: Any) -> dict[str, Any]:
        check_namespace(namespace, self.allowed)
        from kubernetes.client.exceptions import ApiException

        try:
            result: dict[str, Any] = await asyncio.to_thread(action, namespace, *args)
        except ApiException as exc:
            raise RemediationFailed(f"Kubernetes API error {exc.status}: {exc.reason}") from exc
        return result

    async def rollback_deployment(
        self, namespace: str, deployment: str, to_revision: int, *, cause: str
    ) -> dict[str, Any]:
        return await self._run(namespace, self._rollback, deployment, to_revision, cause)

    async def restart_deployment(
        self, namespace: str, deployment: str, *, restarted_at: str
    ) -> dict[str, Any]:
        return await self._run(namespace, self._restart, deployment, restarted_at)

    async def scale_deployment_within_bounds(
        self, namespace: str, deployment: str, replicas: int, *, maximum: int
    ) -> dict[str, Any]:
        if not 1 <= replicas <= maximum:
            raise RemediationFailed(f"{replicas} replicas is outside 1..{maximum}")
        return await self._run(namespace, self._scale, deployment, replicas)
