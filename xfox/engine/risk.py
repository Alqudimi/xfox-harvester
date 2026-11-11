"""Global risk monitor — the engine-wide safety valve.

The monitor is a thin stateful wrapper around the pure
:func:`xfox.domain.policies.evaluate_risk` function. It remembers the current
level, pause state and (optionally) an auto-resume deadline. Transition events
and persistence are handled by the orchestrator so this class stays free of
side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from xfox.domain.enums import RiskLevel
from xfox.domain.policies import RiskAssessment, RiskSettings, RunSignal, evaluate_risk


@dataclass
class RiskMonitor:
    """Current global risk state (mutated only via :meth:`refresh`/:meth:`resume`)."""

    level: RiskLevel = RiskLevel.GREEN
    reasons: list[str] = field(default_factory=list)
    paused: bool = False
    paused_since: datetime | None = None
    auto_resume_at: datetime | None = None

    def refresh(self, signals: list[RunSignal], risk: RiskSettings) -> tuple[bool, RiskAssessment]:
        """Re-evaluate from a window of run signals.

        Returns ``(level_changed, assessment)``. Entering RED pauses the engine;
        if ``auto_resume_minutes`` is configured, a resume deadline is set.
        """
        assessment = evaluate_risk(signals, risk)
        changed = assessment.level != self.level
        self.level = assessment.level
        self.reasons = assessment.reasons

        if assessment.level == RiskLevel.RED and not self.paused:
            now = datetime.now(tz=UTC)
            self.paused = True
            self.paused_since = now
            self.auto_resume_at = (
                now + timedelta(minutes=risk.auto_resume_minutes)
                if risk.auto_resume_minutes > 0
                else None
            )
        elif assessment.level != RiskLevel.RED and self.paused:
            self._clear_pause()

        return changed, assessment

    def maybe_auto_resume(self) -> bool:
        """Resume automatically when the deadline has passed. Returns True if resumed."""
        deadline_reached = (
            self.paused
            and self.auto_resume_at is not None
            and datetime.now(tz=UTC) >= self.auto_resume_at
        )
        if deadline_reached:
            self.resume()
            return True
        return False

    def resume(self) -> None:
        """Manual or automatic resume — the window is reset to GREEN."""
        self._clear_pause()

    def _clear_pause(self) -> None:
        self.paused = False
        self.paused_since = None
        self.auto_resume_at = None
        self.level = RiskLevel.GREEN
        self.reasons = []

    def snapshot(self) -> dict:
        return {
            "level": self.level.value,
            "reasons": list(self.reasons),
            "paused": self.paused,
            "paused_since": self.paused_since,
            "auto_resume_at": self.auto_resume_at,
        }
