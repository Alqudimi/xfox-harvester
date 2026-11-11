"""Anti-ban policy unit tests — the mathematical core of the system."""

from datetime import UTC, datetime, timedelta

import pytest

from xfox.domain.enums import AccountStatus, Aggressiveness, OutcomeKind, RiskLevel, ScheduleKind
from xfox.domain.policies import (
    AccountRuntime,
    ActiveHours,
    AntiBanSettings,
    RiskSettings,
    RunSignal,
    ScheduleSpec,
    account_eligibility,
    apply_outcome_to_account,
    backoff_minutes,
    clamp_to_active_hours,
    compute_next_run,
    effective_daily_cap,
    effective_gap_minutes,
    evaluate_risk,
    jittered_minutes,
    within_active_hours,
)

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class TestJitterAndBackoff:
    def test_jitter_stays_within_bounds(self):
        rng = __import__("random").Random(42)
        for _ in range(200):
            value = jittered_minutes(30, 0.25, rng)
            assert 22.5 <= value <= 37.5

    def test_jitter_never_below_one_minute(self):
        rng = __import__("random").Random(1)
        assert jittered_minutes(1, 0.9, rng) >= 1.0

    def test_backoff_grows_exponentially_until_cap(self):
        rng = __import__("random").Random(7)
        low = backoff_minutes(0, 15, 360, rng)
        high = backoff_minutes(5, 15, 360, rng)
        assert low <= 15 * 1.5
        assert high <= 360 * 1.5

    def test_backoff_always_at_least_one_minute(self):
        rng = __import__("random").Random(3)
        assert backoff_minutes(0, 1, 15, rng) >= 1.0


class TestAggressiveness:
    def test_gap_scaling(self):
        assert effective_gap_minutes(30, Aggressiveness.CAUTIOUS) == pytest.approx(48)
        assert effective_gap_minutes(30, Aggressiveness.BALANCED) == 30
        assert effective_gap_minutes(30, Aggressiveness.FAST) == pytest.approx(18)

    def test_daily_cap_scaling(self):
        assert effective_daily_cap(10, Aggressiveness.CAUTIOUS) == 5
        assert effective_daily_cap(10, Aggressiveness.FAST) == 15
        assert effective_daily_cap(1, Aggressiveness.CAUTIOUS) >= 1


class TestActiveHours:
    def test_disabled_always_active(self):
        assert within_active_hours(NOW, ActiveHours(enabled=False))

    def test_inside_window(self):
        active = ActiveHours(enabled=True, start="08:00", end="23:00")
        assert within_active_hours(NOW, active)

    def test_outside_window(self):
        active = ActiveHours(enabled=True, start="08:00", end="11:00")
        assert not within_active_hours(NOW, active)

    def test_window_wrapping_midnight(self):
        active = ActiveHours(enabled=True, start="22:00", end="06:00")
        night = datetime(2026, 1, 15, 23, 30, tzinfo=UTC)
        morning = datetime(2026, 1, 15, 5, 0, tzinfo=UTC)
        noon = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        assert within_active_hours(night, active)
        assert within_active_hours(morning, active)
        assert not within_active_hours(noon, active)

    def test_clamp_pushes_into_window(self):
        active = ActiveHours(enabled=True, start="08:00", end="22:00")
        late = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
        pushed = clamp_to_active_hours(late, active)
        assert pushed.date() == late.date() + timedelta(days=1)
        assert (pushed.hour, pushed.minute) == (8, 0)


class TestScheduling:
    def test_manual_has_no_next_run(self):
        rng = __import__("random").Random(1)
        assert compute_next_run(ScheduleSpec(), NOW, AntiBanSettings(), Aggressiveness.BALANCED, rng) is None

    def test_interval_respects_global_floor(self):
        rng = __import__("random").Random(1)
        spec = ScheduleSpec(kind=ScheduleKind.INTERVAL, interval_minutes=15)
        # 15 < min_run_gap (30) → the floor applies
        nxt = compute_next_run(spec, NOW, AntiBanSettings(), Aggressiveness.BALANCED, rng)
        assert nxt is not None
        assert nxt - NOW >= timedelta(minutes=30 * 0.75)  # jittered around 30

    def test_daily_advances_to_next_day_when_passed(self):
        rng = __import__("random").Random(1)
        spec = ScheduleSpec(kind=ScheduleKind.DAILY, daily_at="08:00")
        nxt = compute_next_run(spec, NOW, AntiBanSettings(), Aggressiveness.BALANCED, rng)
        assert (nxt.hour, nxt.minute) == (8, 0)
        assert nxt > NOW

    def test_interval_rejects_too_small_values(self):
        with pytest.raises(ValueError):
            ScheduleSpec(kind=ScheduleKind.INTERVAL, interval_minutes=5)


class TestAccountEligibility:
    def _account(self, **overrides) -> AccountRuntime:
        defaults: dict = {
            "account_id": 1,
            "status": AccountStatus.ACTIVE,
            "health_score": 100,
            "cooldown_until": None,
            "last_run_at": None,
            "runs_today": 0,
            "total_runs": 10,
        }
        defaults.update(overrides)
        return AccountRuntime(**defaults)

    def test_fresh_account_is_eligible(self):
        assert account_eligibility(self._account(), NOW, AntiBanSettings()).ok

    def test_cooldown_blocks(self):
        account = self._account(cooldown_until=NOW + timedelta(minutes=10))
        decision = account_eligibility(account, NOW, AntiBanSettings())
        assert not decision.ok
        assert decision.reason == "cooldown"

    def test_daily_cap_blocks(self):
        account = self._account(runs_today=12)
        decision = account_eligibility(account, NOW, AntiBanSettings())
        assert decision.reason == "daily_cap_reached"

    def test_recent_run_blocks_within_gap(self):
        account = self._account(last_run_at=NOW - timedelta(minutes=5))
        decision = account_eligibility(account, NOW, AntiBanSettings())
        assert decision.reason == "min_gap_not_elapsed"

    def test_low_health_blocks(self):
        account = self._account(health_score=10)
        decision = account_eligibility(account, NOW, AntiBanSettings())
        assert decision.reason == "health_too_low"

    def test_warmup_doubles_the_gap(self):
        account = self._account(last_run_at=NOW - timedelta(minutes=31), total_runs=1)
        decision = account_eligibility(account, NOW, AntiBanSettings())
        assert decision.reason == "min_gap_not_elapsed"  # 30 * 2 * 0.6 = 36 minutes floor


class TestHealthDecisions:
    def test_success_heals(self):
        decision = apply_outcome_to_account(
            OutcomeKind.SUCCESS, NOW, AntiBanSettings(), current_score=50
        )
        assert decision.new_score == 52
        assert decision.new_status == AccountStatus.ACTIVE

    def test_rate_limit_cools_down(self):
        decision = apply_outcome_to_account(
            OutcomeKind.RATE_LIMITED, NOW, AntiBanSettings(), current_score=100
        )
        assert decision.new_score == 75
        assert decision.new_status == AccountStatus.COOLDOWN
        assert decision.cooldown_until is not None and decision.cooldown_until > NOW

    def test_auth_expired_streak_disables(self):
        decision = apply_outcome_to_account(
            OutcomeKind.AUTH_EXPIRED,
            NOW,
            AntiBanSettings(),
            current_score=100,
            consecutive_auth_failures=2,  # third strike
        )
        assert decision.new_status == AccountStatus.INVALID

    def test_empty_result_small_penalty_and_cooldown(self):
        decision = apply_outcome_to_account(
            OutcomeKind.EMPTY, NOW, AntiBanSettings(), current_score=100
        )
        assert decision.new_score == 90
        assert decision.cooldown_until is not None

    def test_score_never_leaves_bounds(self):
        low = apply_outcome_to_account(
            OutcomeKind.RATE_LIMITED, NOW, AntiBanSettings(), current_score=0
        )
        high = apply_outcome_to_account(
            OutcomeKind.SUCCESS, NOW, AntiBanSettings(), current_score=100
        )
        assert low.new_score == 0
        assert high.new_score == 100


class TestRiskEvaluation:
    def _signals(self, outcomes, minutes_ago=1):
        when = datetime.now(tz=UTC) - timedelta(minutes=minutes_ago)
        return [RunSignal(outcome, when) for outcome in outcomes]

    def test_below_min_runs_is_green(self):
        signals = self._signals([OutcomeKind.SUCCESS] * 4)
        assert evaluate_risk(signals, RiskSettings()).level == RiskLevel.GREEN

    def test_all_success_stays_green(self):
        signals = self._signals([OutcomeKind.SUCCESS] * 10)
        assert evaluate_risk(signals, RiskSettings()).level == RiskLevel.GREEN

    def test_high_failure_rate_goes_red(self):
        outcomes = [OutcomeKind.RATE_LIMITED] * 4 + [OutcomeKind.SUCCESS] * 6
        assessment = evaluate_risk(self._signals(outcomes), RiskSettings())
        assert assessment.level == RiskLevel.RED
        assert assessment.pauses_engine

    def test_moderate_failures_go_yellow(self):
        outcomes = [OutcomeKind.NETWORK] * 1 + [OutcomeKind.SUCCESS] * 9
        assessment = evaluate_risk(self._signals(outcomes), RiskSettings())
        assert assessment.level == RiskLevel.YELLOW
        assert assessment.throttles

    def test_auth_expired_burst_goes_red(self):
        outcomes = [OutcomeKind.AUTH_EXPIRED] * 3 + [OutcomeKind.SUCCESS] * 7
        assert evaluate_risk(self._signals(outcomes), RiskSettings()).level == RiskLevel.RED

    def test_old_signals_outside_window_ignored(self):
        old = [RunSignal(OutcomeKind.RATE_LIMITED, datetime.now(tz=UTC) - timedelta(hours=6))]
        assert evaluate_risk(old + self._signals([OutcomeKind.SUCCESS] * 6), RiskSettings()).level == RiskLevel.GREEN
