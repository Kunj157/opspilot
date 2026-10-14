"""Read-only Kubernetes access for investigations, limited to allow-listed namespaces.

Only two questions can be asked: a deployment's rollout history and its
current rollout status. There is no generic API access.
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
        raise NamespaceNotAllowed(f"namespace {namespace!r} is not allowed for investigations")


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
