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
from opspilot_api.events.consumer import EventProcessor, KafkaConsumerLoop
from opspilot_api.events.handlers import investigation_requester
from opspilot_api.events.producer import KafkaProducer
from opspilot_api.events.relay import OutboxRelay
from opspilot_api.kube import KubernetesWriter
from opspilot_api.logging import configure_logging
from opspilot_api.ml.shadow import ShadowScorer
from opspilot_api.ops_metrics import LLM_DAILY_BUDGET, POOLS, sample_queues
from opspilot_api.remediation.executor import claim as claim_execution
from opspilot_api.remediation.executor import execute
from opspilot_api.remediation.verification import pending as pending_verifications
from opspilot_api.remediation.verification import verify
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
    POOLS.track("worker", engine)
    LLM_DAILY_BUDGET.set(settings.llm_daily_budget_usd)
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
            # With event-driven investigations the consumer queues them instead.
            auto_investigate=settings.auto_investigate
            and not (settings.kafka_bootstrap_servers and settings.event_driven_investigations),
        )

        async def detect() -> bool:
            await detection.cycle(datetime.now(UTC))
            return False

        loops.append(_loop(stop, "detection", detect, settings.detection_interval_seconds))

        shadow = ShadowScorer.for_prometheus(
            sessions, settings.prometheus_url, settings.allowed_namespaces
        )

        async def score_shadow() -> bool:
            """The ML detector's opinion on every service; stored, never acted on."""
            await shadow.cycle(datetime.now(UTC))
            return False

        loops.append(_loop(stop, "shadow", score_shadow, settings.detection_interval_seconds))

    # Reads for investigations and verification; the three safe actions for remediation.
    writer = KubernetesWriter(
        settings.allowed_namespaces,
        context=settings.kubernetes_context,
        config_file=settings.kubeconfig,
    )
    llm = build_llm(
        settings.llm_provider,
        settings.llm_model,
        settings.llm_base_url,
        settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
    )
    make_context = context_factory(
        sessions,
        metrics=metrics,
        logs=logs,
        traces=traces,
        kube=writer,
        embedder=build_embedder(settings.embedding_model, settings.embedding_cache_dir),
        allowed_namespaces=settings.allowed_namespaces,
        environment=settings.app_env,
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

    async def verify_recovery() -> bool:
        """Look at every remediation awaiting verification once."""
        for execution_id in await pending_verifications(sessions):
            await verify(sessions, writer, metrics, execution_id)
        return False

    loops.append(_loop(stop, "verification", verify_recovery, 10.0))

    async def queue_metrics() -> bool:
        """Refresh the backlog gauges the queue alerts read."""
        await sample_queues(sessions, outbox=bool(settings.kafka_bootstrap_servers))
        return False

    loops.append(_loop(stop, "queue-metrics", queue_metrics, settings.queue_metrics_seconds))

    producer: KafkaProducer | None = None
    if settings.kafka_bootstrap_servers:
        producer = KafkaProducer(settings.kafka_bootstrap_servers)
        relay = OutboxRelay(sessions, producer)

        async def publish() -> bool:
            """Publish the incident timeline; a broker outage just retries next time."""
            return bool(await relay.publish_once())

        loops.append(_loop(stop, "events-relay", publish, 1.0))
        processor = EventProcessor(
            "investigations",
            sessions,
            investigation_requester(
                authoritative=settings.event_driven_investigations and settings.auto_investigate
            ),
            producer,
        )
        loops.append(
            KafkaConsumerLoop(
                processor, settings.kafka_bootstrap_servers, ["incident.created.v1"]
            ).run(stop)
        )

    log.info(
        "worker started", detection=bool(settings.prometheus_url), llm=f"{llm.provider}:{llm.model}"
    )
    try:
        await asyncio.gather(*loops)
    finally:
        for backend in (metrics, logs, traces):
            await backend.aclose()
        await llm.aclose()
        if producer:
            await producer.aclose()
        await engine.dispose()
        log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.model_copy(update={"service_name": "worker"}))
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port, addr=settings.worker_metrics_host)
    asyncio.run(run(settings))
