"""The OpsPilot worker process: detection, investigations, remediation, and postmortems.

    opspilot-worker   (DATABASE_URL required; PROMETHEUS_URL for detection)

Detection runs every DETECTION_INTERVAL_SECONDS. Investigations are claimed
from the database queue as they arrive; with AUTO_INVESTIGATE, every new
detector incident is queued automatically. Approved remediations run as soon
as they are approved, once each.
"""

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import structlog
from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from opspilot_api.agents.investigation import Investigator
from opspilot_api.agents.llm import build_llm
from opspilot_api.agents.postmortem import generate as generate_postmortem
from opspilot_api.agents.postmortem import pending as pending_postmortems
from opspilot_api.agents.runner import InvestigationRunner, context_factory
from opspilot_api.config import Settings, get_settings
from opspilot_api.detection.worker import DetectionWorker
from opspilot_api.kube import KubernetesReader, KubernetesWriter
from opspilot_api.logging import configure_logging
from opspilot_api.remediation.executor import claim as claim_execution
from opspilot_api.remediation.executor import execute
from opspilot_api.runbooks.embeddings import build_embedder
from opspilot_api.telemetry import LokiLogs, PrometheusMetrics, TempoTraces

log = structlog.get_logger("opspilot.worker")


async def _loop(
    stop: asyncio.Event, name: str, step: Callable[[], Awaitable[bool]], idle: float
) -> None:
    while not stop.is_set():
        try:
            busy = await step()
        except Exception:
            # One bad iteration must not stop the worker.
            log.exception("worker iteration failed", loop=name)
            busy = False
        if not busy:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), idle)


async def run(settings: Settings) -> None:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    timeout = settings.telemetry_timeout_seconds
    metrics = PrometheusMetrics(settings.prometheus_url or "http://localhost:9090", timeout=timeout)
    logs = LokiLogs(settings.loki_url or "http://localhost:3100", timeout=timeout)
    traces = TempoTraces(settings.tempo_url or "http://localhost:3200", timeout=timeout)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    loops = []
    if settings.prometheus_url:
        detection = DetectionWorker(
            sessions,
            metrics,
            lag=timedelta(seconds=settings.detection_lag_seconds),
            auto_investigate=settings.auto_investigate,
        )

        async def detect() -> bool:
            await detection.cycle(datetime.now(UTC))
            return False

        loops.append(_loop(stop, "detection", detect, settings.detection_interval_seconds))

    llm = build_llm(
        settings.llm_provider, settings.llm_model, settings.llm_base_url, settings.llm_api_key
    )
    make_context = context_factory(
        sessions,
        metrics=metrics,
        logs=logs,
        traces=traces,
        kube=KubernetesReader(
            settings.allowed_namespaces,
            context=settings.kubernetes_context,
            config_file=settings.kubeconfig,
        ),
        embedder=build_embedder(settings.embedding_model, settings.embedding_cache_dir),
        allowed_namespaces=settings.allowed_namespaces,
    )
    runner = InvestigationRunner(
        sessions,
        lambda: Investigator(
            sessions, llm, make_context, allowed_namespaces=settings.allowed_namespaces
        ),
    )
    loops.append(
        _loop(stop, "investigations", runner.run_once, settings.investigation_poll_seconds)
    )

    async def postmortems() -> bool:
        """Draft postmortems for resolved incidents that lack one or asked for a redraft."""
        incident_ids = await pending_postmortems(sessions)
        for incident_id in incident_ids:
            await generate_postmortem(sessions, llm, incident_id)
        return bool(incident_ids)

    loops.append(_loop(stop, "postmortems", postmortems, 15.0))

    writer = KubernetesWriter(
        settings.allowed_namespaces,
        context=settings.kubernetes_context,
        config_file=settings.kubeconfig,
    )

    async def remediate() -> bool:
        """Run one approved remediation, if any."""
        execution_id = await claim_execution(sessions)
        if execution_id is None:
            return False
        await execute(
            sessions, writer, execution_id, allowed_namespaces=settings.allowed_namespaces
        )
        return True

    loops.append(_loop(stop, "remediation", remediate, 2.0))

    log.info(
        "worker started", detection=bool(settings.prometheus_url), llm=f"{llm.provider}:{llm.model}"
    )
    try:
        await asyncio.gather(*loops)
    finally:
        for backend in (metrics, logs, traces):
            await backend.aclose()
        await llm.aclose()
        await engine.dispose()
        log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.model_copy(update={"service_name": "worker"}))
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port, addr="127.0.0.1")
    asyncio.run(run(settings))
