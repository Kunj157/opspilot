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

    readiness_timeout_seconds: float = 2.0

    def missing_required(self) -> list[str]:
        """Names of required environment variables that are not set."""
        required = {"DATABASE_URL": self.database_url, "REDIS_URL": self.redis_url}
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
