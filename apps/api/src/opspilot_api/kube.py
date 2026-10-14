"""Kubernetes access, limited to allow-listed namespaces.

Investigations get a reader with two questions: a deployment's rollout
history and its current rollout status. Approved remediations get a writer
with four actions: roll back to a revision, restart, scale within bounds,
and pause a rollout. There is no generic API access.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class NamespaceNotAllowed(Exception):
    """The namespace is outside the investigation allow-list."""


@dataclass(frozen=True)
class Revision:
    revision: int
    created_at: datetime | None
    change_cause: str | None
    version: str | None
    image: str | None


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


def check_namespace(namespace: str, allowed: frozenset[str]) -> None:
    if namespace not in allowed:
        raise NamespaceNotAllowed(f"namespace {namespace!r} is not allowed")


def _env(container: Any, name: str) -> str | None:
    for env in container.env or []:
        if env.name == name:
            value: str | None = env.value
            return value
    return None


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
            revisions.append(
                Revision(
                    revision=int(annotations.get("deployment.kubernetes.io/revision", 0)),
                    created_at=rs.metadata.creation_timestamp,
                    change_cause=annotations.get("kubernetes.io/change-cause"),
                    version=_env(container, "SERVICE_VERSION"),
                    image=container.image,
                )
            )
        revisions.sort(key=lambda r: r.revision, reverse=True)
        if revisions:
            # A ReplicaSet reused by a rollback keeps its old creation time; its
            # current pods were created when the latest revision started rolling out.
            started = self._pods_started(namespace, owner, revisions[0].revision)
            latest = revisions[0]
            if started is not None:
                revisions[0] = Revision(
                    latest.revision, started, latest.change_cause, latest.version, latest.image
                )
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

    async def rollout_history(self, namespace: str, deployment: str) -> list[Revision]:
        check_namespace(namespace, self.allowed)
        return await asyncio.to_thread(self._history, namespace, deployment)

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

    async def pause_rollout(self, namespace: str, deployment: str) -> dict[str, Any]: ...


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

    def _pause(self, namespace: str, deployment: str) -> dict[str, Any]:
        # As `kubectl rollout pause`: pods already rolled out keep running, no new ones start.
        self._api().patch_namespaced_deployment(deployment, namespace, {"spec": {"paused": True}})
        return {"paused": True}

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

    async def pause_rollout(self, namespace: str, deployment: str) -> dict[str, Any]:
        return await self._run(namespace, self._pause, deployment)
