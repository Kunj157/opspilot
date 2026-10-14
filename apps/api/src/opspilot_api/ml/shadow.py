"""Shadow scoring: the ML detector judges every service each cycle; nothing acts on it.

Production decisions stay with the error-rate rule. Each prediction is stored
as an anomaly detection with outcome `shadow_alert` or `shadow_normal`, so it
can be compared with the rule's decisions and with real incidents.
"""

import asyncio
import time
from collections.abc import Callable
from datetime import datetime, timedelta

import pandas as pd
import structlog
from opspilot_ml.features import FEATURES, clean
from opspilot_ml.features import fetch as fetch_windows
from prometheus_client import Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from opspilot_api.db.models import AnomalyDetection, Service
from opspilot_api.ml.registry import ModelUnavailable, load_detector, shadow_model

log = structlog.get_logger("opspilot.ml.shadow")

# Enough history for the detector's trailing window (10 minutes) plus slack.
HISTORY = timedelta(minutes=12)
INFERENCE_SECONDS = Histogram(
    "opspilot_ml_inference_seconds", "Time to score every service once with the shadow model"
)

Fetch = Callable[[datetime, datetime], pd.DataFrame]


class ShadowScorer:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        fetch: Fetch,
        namespaces: frozenset[str],
    ) -> None:
        self.sessions = sessions
        self.fetch = fetch
        self.namespaces = namespaces

    @classmethod
    def for_prometheus(
        cls,
        sessions: async_sessionmaker[AsyncSession],
        prometheus_url: str,
        namespaces: frozenset[str],
    ) -> "ShadowScorer":
        return cls(
            sessions, lambda start, end: fetch_windows(prometheus_url, start, end), namespaces
        )

    async def cycle(self, now: datetime) -> int:
        """Score every catalog service once; returns the number of predictions stored."""
        async with self.sessions() as session:
            model = await shadow_model(session)
            if model is None:
                return 0
            services = list(
                await session.scalars(
                    select(Service).where(
                        Service.namespace.in_(self.namespaces),
                        Service.deployment_name.is_not(None),
                    )
                )
            )
        if not services:
            return 0
        try:
            detector = load_detector(model.artifact_uri, model.feature_schema["version"])
        except ModelUnavailable:
            log.warning("shadow model unavailable", model=model.name, version=model.version)
            return 0

        frame = clean(await asyncio.to_thread(self.fetch, now - HISTORY, now))
        if frame.empty:
            return 0
        started = time.perf_counter()
        scores = detector.score(frame)
        alerts = detector.predict(frame)
        INFERENCE_SECONDS.observe(time.perf_counter() - started)

        latest = frame.sort_values("time").groupby("service").tail(1)
        stored = 0
        async with self.sessions() as session:
            for service in services:
                row = latest[latest["service"] == service.deployment_name]
                if row.empty:
                    continue
                index = row.index[0]
                window_end = row["time"].iloc[0].to_pydatetime()
                session.add(
                    AnomalyDetection(
                        organization_id=service.organization_id,
                        service_id=service.id,
                        detector=model.name,
                        failure_category="anomaly",
                        outcome="shadow_alert" if bool(alerts.loc[index]) else "shadow_normal",
                        score=float(scores.loc[index]),
                        threshold=float(detector.threshold),
                        features={name: float(row[name].iloc[0]) for name in FEATURES},
                        model_version=f"{model.name}:{model.version}",
                        window_start=window_end - timedelta(seconds=15),
                        window_end=window_end,
                    )
                )
                stored += 1
            await session.commit()
        return stored
