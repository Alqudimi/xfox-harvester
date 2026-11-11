"""Anti-ban policy engine — pure decision logic, zero I/O.

Everything in this module is deterministic given an injected random source and
the current time, which makes the whole anti-ban brain unit-testable in
milliseconds (see ``tests/test_policies.py``). The engine layer merely feeds
real-world state in and applies the decisions that come out.

Concepts
--------
gaps
    Minimum spacing between two engine runs — per account and globally.
    A random jitter fraction humanizes every gap so the schedule never looks
    robotic.
backoff
    Exponential (base * 2^attempt) with full jitter, capped, applied when a
    run fails — failures never hammer X a second time immediately.
cooldowns
    Forced per-account rest periods after rate-limit signals or empty pages
    (an empty page often means X is soft-throttling the session).
health
    A 0..100 score per X account. Successes slowly heal it, problems drain it;
    below a threshold the account is parked automatically.
risk
    A global GREEN / YELLOW / RED gauge computed from a rolling window of run
    outcomes. YELLOW throttles pacing; RED pauses the engine entirely.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from xfox.domain.enums import (
    AccountStatus,
    Aggressiveness,
    OutcomeKind,
    RiskLevel,
    ScheduleKind,
)

# ---------------------------------------------------------------------------
# Settings models (persisted as JSON in the ``settings`` table)
# ---------------------------------------------------------------------------


class ActiveHours(BaseModel):
    """Daily activity window (server local time). Outside it, scheduled runs wait."""

    enabled: bool = False
    start: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    end: str = Field(default="23:00", pattern=r"^\d{2}:\d{2}$")


class AntiBanSettings(BaseModel):
    """All pacing, backoff, cooldown and health knobs with safe defaults."""

    # --- pacing ---
    min_run_gap_minutes: float = Field(default=30, ge=5, le=720)
    gap_jitter_fraction: float = Field(default=0.25, ge=0.0, le=0.5)
    global_min_gap_minutes: float = Field(default=10, ge=2, le=180)
    max_concurrent_runs: int = Field(default=1, ge=1, le=3)
    max_runs_per_account_per_day: int = Field(default=12, ge=1, le=48)
    run_timeout_minutes: int = Field(default=20, ge=5, le=120)

    # --- failure handling ---
    backoff_base_minutes: float = Field(default=15, ge=1, le=120)
    backoff_cap_minutes: float = Field(default=360, ge=15, le=1440)

    # --- cooldowns after adverse outcomes ---
    rate_limit_cooldown_minutes: float = Field(default=90, ge=10, le=720)
    empty_result_cooldown_minutes: float = Field(default=45, ge=5, le=360)
    error_cooldown_minutes: float = Field(default=30, ge=5, le=360)

    # --- account health ---
    health_on_success: int = Field(default=2, ge=0, le=20)
    health_on_empty: int = Field(default=10, ge=0, le=40)
    health_on_rate_limited: int = Field(default=25, ge=0, le=60)
    health_on_error: int = Field(default=15, ge=0, le=60)
    disable_health_threshold: int = Field(default=15, ge=0, le=50)
    auth_failure_disable_threshold: int = Field(default=3, ge=1, le=10)

    # --- warmup for freshly added accounts ---
    warmup_runs: int = Field(default=3, ge=0, le=20)
    warmup_gap_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)


class RiskSettings(BaseModel):
    """Thresholds for the global risk gauge."""

    window_minutes: int = Field(default=120, ge=15, le=1440)
    min_runs_for_eval: int = Field(default=5, ge=2, le=50)
    yellow_failure_rate: float = Field(default=0.10, ge=0.0, le=1.0)
    red_failure_rate: float = Field(default=0.30, ge=0.0, le=1.0)
    red_rate_limited_count: int = Field(default=5, ge=2, le=50)
    red_auth_expired_count: int = Field(default=3, ge=1, le=20)
    auto_resume_minutes: int = Field(default=0, ge=0, le=720, description="0 = manual resume only")


class CrawlerSettings(BaseModel):
    """X-CrawlFox invocation defaults."""

    headless: bool = True
    default_max_scrolls: int = Field(default=5, ge=1, le=30)
    keep_raw_items: bool = True


class RetentionSettings(BaseModel):
    """Automatic cleanup of operational data."""

    events_days: int = Field(default=30, ge=1, le=365)
    finished_runs_days: int = Field(default=90, ge=1, le=1095)


class AppSettings(BaseModel):
    """Aggregate application settings (the object exposed via the API)."""

    anti_ban: AntiBanSettings = Field(default_factory=AntiBanSettings)
    schedule: ActiveHours = Field(default_factory=ActiveHours)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    retention: RetentionSettings = Field(default_factory=RetentionSettings)


class JobAntiBan(BaseModel):
    """Per-job pacing override (preset on top of the global policy)."""

    aggressiveness: Aggressiveness = Aggressiveness.BALANCED


# ---------------------------------------------------------------------------
# Aggressiveness presets
# ---------------------------------------------------------------------------

_PRESET_GAP_FACTOR: dict[Aggressiveness, float] = {
    Aggressiveness.CAUTIOUS: 1.6,
    Aggressiveness.BALANCED: 1.0,
    Aggressiveness.FAST: 0.6,
}

_PRESET_DAILY_CAP_FACTOR: dict[Aggressiveness, float] = {
    Aggressiveness.CAUTIOUS: 0.5,
    Aggressiveness.BALANCED: 1.0,
    Aggressiveness.FAST: 1.5,
}


def effective_gap_minutes(base_gap_minutes: float, preset: Aggressiveness) -> float:
    """Scale the global minimum gap by a job's aggressiveness preset."""
    return base_gap_minutes * _PRESET_GAP_FACTOR[preset]


def effective_daily_cap(base_cap: int, preset: Aggressiveness) -> int:
    """Scale the per-account daily run cap by a job's aggressiveness preset."""
    return max(1, round(base_cap * _PRESET_DAILY_CAP_FACTOR[preset]))


# ---------------------------------------------------------------------------
# Randomized timing helpers
# ---------------------------------------------------------------------------


def jittered_minutes(base_minutes: float, fraction: float, rng: random.Random) -> float:
    """*base_minutes* perturbed by ±*fraction* (uniform, human-like)."""
    spread = base_minutes * fraction
    return max(1.0, base_minutes + rng.uniform(-spread, spread))


def backoff_minutes(
    attempt: int,
    base_minutes: float,
    cap_minutes: float,
    rng: random.Random,
) -> float:
    """Exponential backoff with full jitter: ``U(0.5, 1.5) * min(cap, base*2^n)``."""
    exponent = min(base_minutes * (2 ** max(0, attempt)), cap_minutes)
    return max(1.0, exponent * rng.uniform(0.5, 1.5))


# ---------------------------------------------------------------------------
# Active-hours window
# ---------------------------------------------------------------------------


def _parse_hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")
    return int(hours), int(minutes)


def within_active_hours(now_local: datetime, active: ActiveHours) -> bool:
    """True when *now_local* falls inside the active window (window may wrap midnight)."""
    if not active.enabled:
        return True
    start_h, start_m = _parse_hhmm(active.start)
    end_h, end_m = _parse_hhmm(active.end)
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    current = now_local.hour * 60 + now_local.minute
    if start <= end:
        return start <= current < end
    return current >= start or current < end  # e.g. 22:00 -> 06:00


def next_window_start(now_local: datetime, active: ActiveHours) -> datetime:
    """The next moment at or after *now_local* inside the active window."""
    if within_active_hours(now_local, active):
        return now_local
    start_h, start_m = _parse_hhmm(active.start)
    candidate = now_local.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleSpec:
    """When a job should run (stored as JSON on the job row)."""

    kind: ScheduleKind = ScheduleKind.MANUAL
    interval_minutes: int | None = None  # required for INTERVAL
    daily_at: str | None = None          # "HH:MM", required for DAILY

    def __post_init__(self) -> None:
        if self.kind == ScheduleKind.INTERVAL and (
            not self.interval_minutes or self.interval_minutes < 15
        ):
            raise ValueError("interval_minutes must be >= 15 for interval schedules")
        if self.kind == ScheduleKind.DAILY and (not self.daily_at or ":" not in self.daily_at):
            raise ValueError("daily_at (HH:MM) is required for daily schedules")

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleSpec:
        """Rebuild a spec from its JSON representation (as stored on jobs)."""
        return cls(
            kind=ScheduleKind(data.get("kind", ScheduleKind.MANUAL.value)),
            interval_minutes=data.get("interval_minutes"),
            daily_at=data.get("daily_at"),
        )


def _next_daily_occurrence(now_local: datetime, at: str) -> datetime:
    hours, minutes = _parse_hhmm(at)
    candidate = now_local.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


def compute_next_run(
    schedule: ScheduleSpec,
    now: datetime,
    anti_ban: AntiBanSettings,
    preset: Aggressiveness,
    rng: random.Random,
    last_run_at: datetime | None = None,
) -> datetime | None:
    """Compute the next run time for a job.

    Interval schedules add a jittered gap to ``max(now, last_run_at)``; daily
    schedules fire at the next occurrence. The result is pushed into the
    active-hours window when one is configured. Manual jobs return ``None``.
    """
    if schedule.kind == ScheduleKind.MANUAL:
        return None

    if schedule.kind == ScheduleKind.INTERVAL:
        base_gap = effective_gap_minutes(float(schedule.interval_minutes or 30), preset)
        # interval jobs also respect the global minimum gap as a floor
        base_gap = max(base_gap, anti_ban.min_run_gap_minutes * _PRESET_GAP_FACTOR[preset])
        gap = timedelta(minutes=jittered_minutes(base_gap, anti_ban.gap_jitter_fraction, rng))
        anchor = max(last_run_at, now) if last_run_at else now
        candidate = anchor + gap
    else:  # DAILY
        candidate = _next_daily_occurrence(now, schedule.daily_at or "08:00")

    return candidate


def clamp_to_active_hours(candidate: datetime, active: ActiveHours) -> datetime:
    """Push *candidate* forward until it sits inside the active window (tz-aware)."""
    if not active.enabled:
        return candidate
    local = candidate.astimezone() if candidate.tzinfo else candidate
    if within_active_hours(local, active):
        return candidate
    pushed = next_window_start(local, active)
    return pushed.replace(tzinfo=local.tzinfo).astimezone(UTC) if candidate.tzinfo else pushed


# ---------------------------------------------------------------------------
# Account health & eligibility
# ---------------------------------------------------------------------------


@dataclass
class AccountRuntime:
    """Snapshot of an account's live state used for eligibility decisions."""

    account_id: int
    status: AccountStatus
    health_score: int = 100
    cooldown_until: datetime | None = None
    last_run_at: datetime | None = None
    runs_today: int = 0
    total_runs: int = 0
    consecutive_auth_failures: int = 0


@dataclass(frozen=True)
class Eligibility:
    ok: bool
    reason: str = ""


_GAP_FLOOR_FRACTION = 0.6  # eligibility uses 60% of the nominal gap (jitter tolerance)


def account_eligibility(
    account: AccountRuntime,
    now: datetime,
    anti_ban: AntiBanSettings,
    preset: Aggressiveness = Aggressiveness.BALANCED,
) -> Eligibility:
    """Decide whether an account may be picked for a new run right now."""
    if account.status == AccountStatus.DISABLED:
        return Eligibility(False, "disabled")
    if account.status == AccountStatus.INVALID:
        return Eligibility(False, "invalid_cookies")
    if account.cooldown_until and account.cooldown_until > now:
        return Eligibility(False, "cooldown")
    if account.runs_today >= effective_daily_cap(
        anti_ban.max_runs_per_account_per_day, preset
    ):
        return Eligibility(False, "daily_cap_reached")
    if account.last_run_at:
        base_gap = anti_ban.min_run_gap_minutes * _PRESET_GAP_FACTOR[preset]
        if account.total_runs < anti_ban.warmup_runs:
            base_gap *= anti_ban.warmup_gap_multiplier
        floor = timedelta(minutes=base_gap * _GAP_FLOOR_FRACTION)
        if now - account.last_run_at < floor:
            return Eligibility(False, "min_gap_not_elapsed")
    if account.health_score <= anti_ban.disable_health_threshold:
        return Eligibility(False, "health_too_low")
    return Eligibility(True, "")


@dataclass(frozen=True)
class HealthDecision:
    new_score: int
    new_status: AccountStatus
    cooldown_until: datetime | None


def apply_outcome_to_account(
    outcome: OutcomeKind,
    now: datetime,
    anti_ban: AntiBanSettings,
    current_score: int = 100,
    current_status: AccountStatus = AccountStatus.ACTIVE,
    consecutive_auth_failures: int = 0,
) -> HealthDecision:
    """Translate a run outcome into the account's next health state."""
    score = current_score
    status = current_status if current_status != AccountStatus.COOLDOWN else AccountStatus.ACTIVE
    cooldown: datetime | None = None
    auth_streak = consecutive_auth_failures

    if outcome == OutcomeKind.SUCCESS:
        score += anti_ban.health_on_success
        auth_streak = 0
    elif outcome == OutcomeKind.EMPTY:
        score -= anti_ban.health_on_empty
        cooldown = now + timedelta(
            minutes=jittered_minutes(anti_ban.empty_result_cooldown_minutes, 0.25, _rng())
        )
    elif outcome == OutcomeKind.RATE_LIMITED:
        score -= anti_ban.health_on_rate_limited
        status = AccountStatus.COOLDOWN
        cooldown = now + timedelta(
            minutes=jittered_minutes(anti_ban.rate_limit_cooldown_minutes, 0.25, _rng())
        )
    elif outcome == OutcomeKind.AUTH_EXPIRED:
        auth_streak += 1
        score = 0
        if auth_streak >= anti_ban.auth_failure_disable_threshold:
            status = AccountStatus.INVALID
        else:
            status = AccountStatus.COOLDOWN
            cooldown = now + timedelta(minutes=anti_ban.rate_limit_cooldown_minutes)
    else:  # TIMEOUT / NETWORK / BROWSER / UNKNOWN_ERROR
        score -= anti_ban.health_on_error
        status = AccountStatus.COOLDOWN
        cooldown = now + timedelta(
            minutes=jittered_minutes(anti_ban.error_cooldown_minutes, 0.25, _rng())
        )

    score = max(0, min(100, score))
    if score <= anti_ban.disable_health_threshold and status not in (
        AccountStatus.INVALID,
        AccountStatus.DISABLED,
    ):
        status = AccountStatus.COOLDOWN
        cooldown = (cooldown or now) + timedelta(hours=6)

    return HealthDecision(score, status, cooldown)


def _rng() -> random.Random:
    """Module-level RNG for cooldown jitter (tests monkeypatch this)."""
    return random.SystemRandom()


# ---------------------------------------------------------------------------
# Global risk evaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunSignal:
    """One finished run, feeding the risk gauge."""

    outcome: OutcomeKind
    finished_at: datetime


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)

    @property
    def pauses_engine(self) -> bool:
        return self.level == RiskLevel.RED

    @property
    def throttles(self) -> bool:
        return self.level == RiskLevel.YELLOW


_FAILURE_OUTCOMES = frozenset(
    {
        OutcomeKind.RATE_LIMITED,
        OutcomeKind.AUTH_EXPIRED,
        OutcomeKind.NETWORK,
        OutcomeKind.BROWSER,
        OutcomeKind.TIMEOUT,
        OutcomeKind.UNKNOWN_ERROR,
    }
)


def evaluate_risk(signals: list[RunSignal], risk: RiskSettings) -> RiskAssessment:
    """Evaluate the global risk gauge over a rolling window of run outcomes."""
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=risk.window_minutes)
    recent = [s for s in signals if s.finished_at >= cutoff]
    if len(recent) < risk.min_runs_for_eval:
        return RiskAssessment(RiskLevel.GREEN)

    failures = [s for s in recent if s.outcome in _FAILURE_OUTCOMES]
    rate_limited = sum(1 for s in recent if s.outcome == OutcomeKind.RATE_LIMITED)
    auth_expired = sum(1 for s in recent if s.outcome == OutcomeKind.AUTH_EXPIRED)
    failure_rate = len(failures) / len(recent)
    reasons: list[str] = []

    if (
        failure_rate >= risk.red_failure_rate
        or rate_limited >= risk.red_rate_limited_count
        or auth_expired >= risk.red_auth_expired_count
    ):
        if failure_rate >= risk.red_failure_rate:
            reasons.append(f"failure_rate={failure_rate:.0%}")
        if rate_limited >= risk.red_rate_limited_count:
            reasons.append(f"rate_limited={rate_limited}")
        if auth_expired >= risk.red_auth_expired_count:
            reasons.append(f"auth_expired={auth_expired}")
        return RiskAssessment(RiskLevel.RED, reasons)

    if failure_rate >= risk.yellow_failure_rate or rate_limited >= 2 or auth_expired >= 1:
        if failure_rate >= risk.yellow_failure_rate:
            reasons.append(f"failure_rate={failure_rate:.0%}")
        if rate_limited >= 2:
            reasons.append(f"rate_limited={rate_limited}")
        if auth_expired >= 1:
            reasons.append(f"auth_expired={auth_expired}")
        return RiskAssessment(RiskLevel.YELLOW, reasons)

    return RiskAssessment(RiskLevel.GREEN)
