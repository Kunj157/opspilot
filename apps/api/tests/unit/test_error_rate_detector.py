"""The error-rate rule: persistence, low traffic, hysteresis, cooldown, missing data."""

from opspilot_api.detection.rules import (
    DetectorState,
    ErrorRateRule,
    Outcome,
    Window,
)

RULE = ErrorRateRule(
    min_requests_per_second=0.5,
    threshold=0.05,
    recovery_threshold=0.02,
    trigger_windows=3,
    recovery_windows=3,
    cooldown_windows=4,
)

HEALTHY = Window(requests_per_second=5.0, error_rate=0.0)
BAD = Window(requests_per_second=5.0, error_rate=0.4)
BORDERLINE = Window(requests_per_second=5.0, error_rate=0.03)
QUIET_BAD = Window(requests_per_second=0.1, error_rate=1.0)
MISSING = Window(requests_per_second=None, error_rate=None)


def run(windows: list[Window], state: DetectorState | None = None) -> list[Outcome]:
    state = state or DetectorState()
    outcomes = []
    for window in windows:
        state, decision = RULE.evaluate(state, window)
        outcomes.append(decision.outcome)
    return outcomes


def test_healthy_traffic_never_triggers() -> None:
    assert set(run([HEALTHY] * 20)) == {Outcome.NONE}


def test_rates_below_the_threshold_never_trigger() -> None:
    assert set(run([BORDERLINE] * 20)) == {Outcome.NONE}


def test_low_traffic_never_triggers_even_when_every_request_fails() -> None:
    assert set(run([QUIET_BAD] * 20)) == {Outcome.NONE}


def test_a_single_spike_does_not_trigger() -> None:
    assert set(run([HEALTHY, BAD, HEALTHY, BAD, HEALTHY, BAD, HEALTHY])) == {Outcome.NONE}


def test_a_persistent_breach_triggers_once_then_updates() -> None:
    assert run([BAD] * 5) == [
        Outcome.NONE,
        Outcome.NONE,
        Outcome.TRIGGERED,
        Outcome.ONGOING,
        Outcome.ONGOING,
    ]


def test_low_traffic_interrupts_the_breach_streak() -> None:
    assert Outcome.TRIGGERED not in run([BAD, BAD, QUIET_BAD, BAD, BAD])


def test_missing_windows_neither_trigger_nor_reset() -> None:
    assert run([BAD, MISSING, BAD, MISSING, BAD]) == [
        Outcome.NONE,
        Outcome.NONE,
        Outcome.NONE,
        Outcome.NONE,
        Outcome.TRIGGERED,
    ]


def test_recovery_needs_consecutive_healthy_windows() -> None:
    outcomes = run([BAD] * 3 + [HEALTHY, HEALTHY, BAD, HEALTHY, HEALTHY, HEALTHY])

    assert outcomes[-1] is Outcome.RECOVERED
    assert outcomes.count(Outcome.RECOVERED) == 1


def test_hysteresis_band_keeps_the_incident_open() -> None:
    outcomes = run([BAD] * 3 + [BORDERLINE] * 10)

    assert Outcome.RECOVERED not in outcomes


def test_missing_data_does_not_recover() -> None:
    outcomes = run([BAD] * 3 + [MISSING] * 10)

    assert Outcome.RECOVERED not in outcomes


def test_cooldown_suppresses_an_immediate_retrigger() -> None:
    outcomes = run([BAD] * 3 + [HEALTHY] * 3 + [BAD] * 3)

    assert outcomes.count(Outcome.TRIGGERED) == 1


def test_after_the_cooldown_a_new_breach_triggers_again() -> None:
    outcomes = run([BAD] * 3 + [HEALTHY] * 3 + [HEALTHY] * 4 + [BAD] * 3)

    assert outcomes.count(Outcome.TRIGGERED) == 2


def test_decisions_carry_score_and_features() -> None:
    state = DetectorState()
    for window in [BAD] * 3:
        state, decision = RULE.evaluate(state, window)

    assert decision.score == 8.0
    assert decision.features == {"error_rate": 0.4, "requests_per_second": 5.0}
    assert decision.threshold == 0.05


def test_state_round_trips_through_json() -> None:
    state = DetectorState()
    for window in [BAD] * 2:
        state, _ = RULE.evaluate(state, window)

    assert DetectorState.model_validate_json(state.model_dump_json()) == state
