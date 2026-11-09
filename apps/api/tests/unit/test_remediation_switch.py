"""The remediation kill switch (ADR-003 section 6): off by default, approval always required."""

import pytest
from pydantic import ValidationError

from opspilot_api.config import Settings


def test_remediation_is_off_by_default() -> None:
    assert Settings().remediation_enabled is False


def test_the_switch_reads_remediation_enabled_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REMEDIATION_ENABLED", "true")

    assert Settings().remediation_enabled is True


def test_approval_is_required_by_default() -> None:
    assert Settings().require_remediation_approval is True


@pytest.mark.parametrize("value", ["false", "0"])
def test_approval_cannot_be_switched_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("REQUIRE_REMEDIATION_APPROVAL", value)

    with pytest.raises(ValidationError, match="every remediation needs"):
        Settings()
