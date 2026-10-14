"""Event-driven stages: on by default with a broker, polling without one, shadow when false."""

import pytest

from opspilot_api.config import Settings

BROKER = "redpanda:9092"


def test_without_a_broker_every_stage_polls() -> None:
    settings = Settings(kafka_bootstrap_servers=None, event_driven_remediation=True)

    assert not settings.investigations_by_event
    assert not settings.remediation_by_event
    assert not settings.verification_by_event


def test_with_a_broker_every_stage_is_event_driven_by_default() -> None:
    settings = Settings(kafka_bootstrap_servers=BROKER)

    assert settings.investigations_by_event
    assert settings.remediation_by_event
    assert settings.verification_by_event


def test_a_stage_set_to_false_stays_in_shadow_mode() -> None:
    settings = Settings(kafka_bootstrap_servers=BROKER, event_driven_verification=False)

    assert settings.remediation_by_event
    assert not settings.verification_by_event


def test_empty_environment_values_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", BROKER)
    monkeypatch.setenv("EVENT_DRIVEN_INVESTIGATIONS", "")
    monkeypatch.setenv("EVENT_DRIVEN_REMEDIATION", "false")

    settings = Settings()

    assert settings.event_driven_investigations is None
    assert settings.investigations_by_event
    assert not settings.remediation_by_event
