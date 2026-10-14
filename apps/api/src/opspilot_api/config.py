from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    service_name: str = "api"
    log_level: str = "INFO"

    database_url: str | None = None
    redis_url: str | None = None

    jwt_issuer: str | None = None
    jwt_audience: str | None = None

    # Comma-separated addresses allowed to set X-Forwarded-For (the web app's proxy).
    trusted_proxies: str = "127.0.0.1"

    # Observability backends (read-only). Optional: the API runs without them.
    prometheus_url: str | None = None
    loki_url: str | None = None
    tempo_url: str | None = None
    telemetry_timeout_seconds: float = 5.0

    # Runbook embeddings: a fastembed model name, or "hashing" (deterministic, for tests).
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str | None = None

    # Detection worker
    detection_interval_seconds: float = 15.0
    # Prometheus scrapes every 10 s; this keeps the newest sample in each window.
    detection_lag_seconds: float = 15.0
    worker_metrics_port: int | None = None
    # 0.0.0.0 in containers, so the cluster's probes and Prometheus can reach it.
    worker_metrics_host: str = "127.0.0.1"
    # Touched while the database is reachable; the readiness probe checks its age.
    worker_heartbeat_file: str | None = None
    worker_heartbeat_seconds: float = 10.0
    # Queue an agent investigation for every new detector incident.
    auto_investigate: bool = True
    investigation_poll_seconds: float = 2.0

    # Investigation agents: "ollama" (local, default), "anthropic", or "scripted" (tests).
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_timeout_seconds: float = 120.0

    # Investigations may only read (and, in phase 9, remediate) these namespaces.
    agent_allowed_namespaces: str = "demo"
    kubernetes_context: str | None = None
    kubeconfig: str | None = None

    # Event broker (Redpanda). Unset: no events are published or consumed.
    kafka_bootstrap_servers: str | None = None
    # When true, detector incidents are investigated from incident.created
    # events instead of the direct call (which is then skipped).
    event_driven_investigations: bool = False

    # Rate limits (Redis, shared by all replicas): requests per window. Reads,
    # mutations, and sensitive actions are counted per user; requests without a
    # token and rejected tokens per client IP.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_read: int = 1200
    rate_limit_write: int = 300
    rate_limit_sensitive: int = 30
    rate_limit_anonymous: int = 300
    rate_limit_auth_failures: int = 30

    readiness_timeout_seconds: float = 2.0
    sse_heartbeat_seconds: float = 15.0

    @property
    def allowed_namespaces(self) -> frozenset[str]:
        return frozenset(n.strip() for n in self.agent_allowed_namespaces.split(",") if n.strip())

    def missing_required(self) -> list[str]:
        """Names of required environment variables that are not set."""
        required = {
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "JWT_ISSUER": self.jwt_issuer,
            "JWT_AUDIENCE": self.jwt_audience,
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
