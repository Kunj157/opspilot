"""Detection rules: pure functions from (state, window) to (state, decision).

A window is one evaluation of a service's recent traffic. Rules never do I/O,
so every behaviour (persistence, hysteresis, cooldown) is unit-tested.
"""

import enum
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict


class Outcome(enum.StrEnum):
    NONE = "none"
    TRIGGERED = "triggered"
    ONGOING = "ongoing"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class Window:
    """Rates over one evaluation window; None when the data is not there yet."""

    requests_per_second: float | None
    error_rate: float | None

    @property
    def missing(self) -> bool:
        return self.requests_per_second is None or self.error_rate is None


class DetectorState(BaseModel):
    """Per service and rule; persisted between cycles so restarts do not re-trigger."""

    model_config = ConfigDict(frozen=True)

    active: bool = False
    breach_streak: int = 0
    healthy_streak: int = 0
    cooldown: int = 0


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    score: float | None = None
    threshold: float | None = None
    features: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorRateRule:
    """Sustained HTTP error rate on a service with real traffic.

    Triggers after `trigger_windows` consecutive windows at or above
    `threshold` with at least `min_requests_per_second`. Recovers after
    `recovery_windows` consecutive windows below `recovery_threshold`
    (the gap is hysteresis), then waits `cooldown_windows` before it can
    trigger again.
    """

    min_requests_per_second: float = 0.5
    threshold: float = 0.05
    recovery_threshold: float = 0.02
    trigger_windows: int = 3
    recovery_windows: int = 3
    cooldown_windows: int = 8

    name = "error-rate"
    failure_category = "high_error_rate"

    def evaluate(self, state: DetectorState, window: Window) -> tuple[DetectorState, Decision]:
        if window.missing:
            return state, Decision(Outcome.NONE)
        rps = window.requests_per_second or 0.0
        rate = window.error_rate or 0.0
        decision = Decision(
            Outcome.NONE,
            score=round(rate / self.threshold, 4),
            threshold=self.threshold,
            features={"error_rate": rate, "requests_per_second": rps},
        )
        enough_traffic = rps >= self.min_requests_per_second
        breaching = enough_traffic and rate >= self.threshold

        if state.active:
            if breaching:
                return state.model_copy(update={"healthy_streak": 0}), _with(
                    decision, Outcome.ONGOING
                )
            if enough_traffic and rate < self.recovery_threshold:
                healthy = state.healthy_streak + 1
                if healthy >= self.recovery_windows:
                    recovered = DetectorState(cooldown=self.cooldown_windows)
                    return recovered, _with(decision, Outcome.RECOVERED)
                return state.model_copy(update={"healthy_streak": healthy}), decision
            # Low traffic or inside the hysteresis band: no evidence of recovery.
            return state.model_copy(update={"healthy_streak": 0}), decision

        cooldown = max(0, state.cooldown - 1)
        streak = state.breach_streak + 1 if breaching else 0
        if streak >= self.trigger_windows and state.cooldown == 0:
            triggered = DetectorState(active=True)
            return triggered, _with(decision, Outcome.TRIGGERED)
        return DetectorState(breach_streak=streak, cooldown=cooldown), decision


def _with(decision: Decision, outcome: Outcome) -> Decision:
    return Decision(outcome, decision.score, decision.threshold, decision.features)
