from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ServiceName = Literal["storefront", "checkout", "payment", "inventory", "notification"]


class Settings(BaseSettings):
    """Per-service configuration, from environment variables in the cluster."""

    model_config = SettingsConfigDict(frozen=True)

    service_name: ServiceName
    service_version: str = "1.0.0"
    environment: str = "local"
    # OTLP/HTTP collector endpoint; traces are not exported when unset.
    otlp_endpoint: str | None = None
    # Faults come only from configuration, so a faulty release is a new
    # rollout revision and rolling back removes it.
    fault_error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    fault_latency_ms: int = Field(default=0, ge=0, le=30_000)
    request_timeout_seconds: float = Field(default=2.0, gt=0)
    # Base URLs of the other services; Kubernetes service DNS names by default.
    checkout_url: str = "http://checkout"
    payment_url: str = "http://payment"
    inventory_url: str = "http://inventory"
    notification_url: str = "http://notification"
    k8s_namespace: str | None = None
    k8s_pod_name: str | None = None
