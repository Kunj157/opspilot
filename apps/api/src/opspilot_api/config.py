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

    readiness_timeout_seconds: float = 2.0
    sse_heartbeat_seconds: float = 15.0

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
