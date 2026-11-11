"""Account pool — choosing the safest X account for the next run.

Selection strategy: among every *eligible* account (see
:func:`xfox.domain.policies.account_eligibility`) we prefer the one that has
been resting the longest (least-recently-used), breaking ties by health. This
spreads load across accounts exactly like a careful human team would.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import XAccountRow
from xfox.db.repo import accounts as accounts_repo
from xfox.db.repo import runs as runs_repo
from xfox.domain.enums import AccountStatus, Aggressiveness
from xfox.domain.policies import AntiBanSettings, account_eligibility


class AccountPool:
    """Picks accounts for runs while honoring every anti-ban constraint."""

    async def select(
        self,
        session: AsyncSession,
        anti_ban: AntiBanSettings,
        preset: Aggressiveness = Aggressiveness.BALANCED,
        pinned_account_id: int | None = None,
    ) -> tuple[XAccountRow | None, str]:
        """Return ``(account, reason)`` — account is ``None`` when unavailable."""
        accounts = await accounts_repo.list_accounts(session)
        if not accounts:
            return None, "no_accounts"

        runs_today = await runs_repo.runs_today_by_account(session)
        streaks = await runs_repo.consecutive_auth_failures(session)
        now = datetime.now(tz=UTC)

        eligible: list[tuple[XAccountRow, float]] = []
        for row in accounts:
            if pinned_account_id is not None and row.id != pinned_account_id:
                continue
            if not row.has_cookies:
                continue
            runtime = self._runtime(row, runs_today, streaks)
            decision = account_eligibility(runtime, now, anti_ban, preset)
            if decision.ok:
                eligible.append((row, self._preference_key(row)))
            elif pinned_account_id == row.id:
                return None, decision.reason

        if not eligible:
            return None, "no_eligible_account"

        eligible.sort(key=lambda pair: pair[1])
        return eligible[0][0], ""

    @staticmethod
    def _runtime(
        row: XAccountRow,
        runs_today: dict[int, int],
        streaks: dict[int, int],
    ):
        from xfox.domain.policies import AccountRuntime

        return AccountRuntime(
            account_id=row.id,
            status=AccountStatus(row.status),
            health_score=row.health_score,
            cooldown_until=row.cooldown_until,
            last_run_at=row.last_run_at,
            runs_today=runs_today.get(row.id, 0),
            total_runs=int((row.stats or {}).get("total_runs", 0)),
            consecutive_auth_failures=streaks.get(row.id, 0),
        )

    @staticmethod
    def _preference_key(row: XAccountRow) -> float:
        """Sort key: never-used accounts first, then longest-resting, healthiest."""
        if row.last_run_at is None:
            return float("-inf")
        return row.last_run_at.timestamp() - row.health_score * 0.1
