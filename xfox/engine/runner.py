"""Job runner — executes one job run end-to-end.

Pipeline: mark RUNNING → prepare workspace & crawl config → invoke X-CrawlFox
(streaming its log) → classify the outcome → ingest harvested items → apply
account health + risk policies → schedule the job's next run → emit events.

The runner never talks to X directly; everything browser-related happens in the
X-CrawlFox subprocess (Camoufox with fingerprint obfuscation and humanized
browsing — the first line of defense against bans). The runner is the second
line: pacing, cooldowns, health scoring and the global risk gauge.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xfox.config import settings as app_config
from xfox.db.models import JobRow, JobRunRow, XAccountRow
from xfox.db.repo import accounts as accounts_repo
from xfox.db.repo import jobs as jobs_repo
from xfox.db.repo import posts as posts_repo
from xfox.db.repo import runs as runs_repo
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import (
    AccountStatus,
    EventCategory,
    EventLevel,
    EventType,
    JobType,
    OutcomeKind,
    RunStatus,
)
from xfox.domain.policies import (
    AppSettings,
    ScheduleSpec,
    apply_outcome_to_account,
    backoff_minutes,
    clamp_to_active_hours,
    compute_next_run,
)
from xfox.domain.schemas import JobAntiBanModel
from xfox.engine.events import build_event_payload, bus, emit_event
from xfox.engine.ingest import map_items
from xfox.engine.outcomes import analyze_log
from xfox.engine.workspaces import WorkspaceManager
from xfox.engine.xcrawlfox import XCrawlFoxAdapter

_OUTCOME_TO_STATUS: dict[OutcomeKind, RunStatus] = {
    OutcomeKind.SUCCESS: RunStatus.SUCCESS,
    OutcomeKind.EMPTY: RunStatus.EMPTY,
    OutcomeKind.CANCELLED: RunStatus.CANCELLED,
    OutcomeKind.TIMEOUT: RunStatus.TIMEOUT,
    OutcomeKind.RATE_LIMITED: RunStatus.FAILED,
    OutcomeKind.AUTH_EXPIRED: RunStatus.FAILED,
    OutcomeKind.NETWORK: RunStatus.FAILED,
    OutcomeKind.BROWSER: RunStatus.FAILED,
    OutcomeKind.UNKNOWN_ERROR: RunStatus.FAILED,
}

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

_LOG_EXCERPT_LINES = 40


class JobRunner:
    """Runs a single job execution to completion (or timeout/cancel)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        adapter: XCrawlFoxAdapter | None = None,
    ) -> None:
        self._sessions = session_factory
        self.adapter = adapter or XCrawlFoxAdapter()
        self.workspaces = WorkspaceManager()
        self._rng = random.Random()

    # ------------------------------------------------------------------

    async def execute(self, run_id: int) -> None:
        """Execute the queued run *run_id* and persist every decision."""
        async with self._sessions() as session:
            run = await runs_repo.get_run(session, run_id)
            if run is None or run.status != RunStatus.QUEUED:
                return
            job = await jobs_repo.get_job(session, run.job_id)
            account = (
                await accounts_repo.get_account(session, run.account_id)
                if run.account_id
                else None
            )
            app_settings = await settings_repo.load_app_settings(session)
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(tz=UTC)
            await session.commit()

        if job is None or account is None:
            await self._skip_run(run_id, "missing_job_or_account")
            return

        await emit_safe(
            EventType.RUN_STARTED,
            EventLevel.INFO,
            EventCategory.RUN,
            f"Run #{run.id} started for job '{job.name}' on account '{account.label}'",
            params={"job": job.name, "account": account.label},
            job_id=job.id,
            run_id=run.id,
            account_id=account.id,
        )

        result_summary = await self._invoke(run, job, account, app_settings)
        await self._finalize(run_id, job.id, account.id, app_settings, result_summary)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------

    async def _invoke(
        self, run: JobRunRow, job: JobRow, account: XAccountRow, app_settings: AppSettings
    ) -> dict[str, Any]:
        crawler = app_settings.crawler
        anti_ban = app_settings.anti_ban

        self.workspaces.ensure(account.id)
        self.workspaces.clean_output(account.id)
        crawl_config = self.adapter.build_crawl_config(JobType(job.type), job.config, crawler)
        config_path = self.workspaces.write_crawl_config(account.id, crawl_config)

        proxy_url = self._proxy_url(account)
        log_path = self._run_log_path(run.id)
        log_lines: list[str] = []

        def on_log(line: str) -> None:
            log_lines.append(line)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            bus.publish(
                build_event_payload(
                    event_id=None,
                    type=EventType.RUN_LOG,
                    level=EventLevel.INFO,
                    category=EventCategory.RUN,
                    message=line,
                    params={},
                    account_id=account.id,
                    job_id=job.id,
                    run_id=run.id,
                )
            )

        result = await self.adapter.execute(
            account_id=account.id,
            config_path=config_path,
            headless=crawler.headless,
            proxy_url=proxy_url,
            timeout_minutes=anti_ban.run_timeout_minutes,
            on_log=on_log,
        )

        raw_items: list[dict[str, Any]] = []
        if not result.timed_out and not result.cancelled:
            raw_items = self.workspaces.read_output_items(account.id)
        posts, skipped = map_items(raw_items)

        analysis = analyze_log(
            result.log_text,
            timed_out=result.timed_out,
            cancelled=result.cancelled,
            items_collected=len(posts),
        )

        return {
            "analysis": analysis,
            "posts": posts,
            "skipped_items": skipped,
            "duration_ms": result.duration_ms,
            "log_lines": log_lines,
            "log_text": result.log_text,
        }

    @staticmethod
    def _proxy_url(account: XAccountRow) -> str | None:
        proxy = account.proxy
        if proxy is not None and proxy.status == "active":
            return proxy.url
        return None

    @staticmethod
    def _run_log_path(run_id: int) -> Path:
        directory = app_config.run_logs_dir
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"run-{run_id}.log"

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    async def _finalize(
        self,
        run_id: int,
        job_id: int,
        account_id: int,
        app_settings: AppSettings,
        summary: dict[str, Any],
    ) -> None:
        analysis = summary["analysis"]
        posts = summary["posts"]
        outcome = analysis.outcome

        items_new = 0
        if posts and outcome in (OutcomeKind.SUCCESS, OutcomeKind.EMPTY):
            async with self._sessions() as session:
                items_new, _total = await posts_repo.ingest_posts(
                    session,
                    posts,
                    run_id=run_id,
                    keep_raw=app_settings.crawler.keep_raw_items,
                )
                await session.commit()

        now = datetime.now(tz=UTC)
        async with self._sessions() as session:
            run = await runs_repo.get_run(session, run_id)
            job = await jobs_repo.get_job(session, job_id)
            account = await accounts_repo.get_account(session, account_id)
            if run is None:
                return

            run.status = _OUTCOME_TO_STATUS.get(outcome, RunStatus.FAILED)
            run.finished_at = now
            run.items_new = items_new
            run.items_total = len(posts)
            run.duration_ms = summary["duration_ms"]
            run.outcome = {
                "kind": outcome.value,
                "message": analysis.message,
                "signals": analysis.signals,
            }
            run.log_excerpt = "\n".join(summary["log_lines"][-_LOG_EXCERPT_LINES:])
            if analysis.saved_path:
                run.output_file = Path(analysis.saved_path).name

            if job is not None:
                await self._schedule_next(session, job, outcome, app_settings, now)
            if account is not None:
                await self._apply_account_health(
                session, account, outcome, app_settings, now, items_new
            )

            await session.commit()

        await self._emit_finish_events(
            job_id, account_id, run_id, outcome, items_new, len(posts), summary
        )

    async def _schedule_next(
        self,
        session: AsyncSession,
        job: JobRow,
        outcome: OutcomeKind,
        app_settings: AppSettings,
        now: datetime,
    ) -> None:
        """Set the job's next run — backoff on failure, schedule otherwise."""
        stats = dict(job.stats or {})
        if outcome in _FAILURE_OUTCOMES:
            failures = int(stats.get("consecutive_failures", 0)) + 1
            delay = backoff_minutes(
                failures,
                app_settings.anti_ban.backoff_base_minutes,
                app_settings.anti_ban.backoff_cap_minutes,
                self._rng,
            )
            next_run = now + timedelta(minutes=delay)
            stats["consecutive_failures"] = failures
            stats["last_backoff_minutes"] = round(delay, 1)
        else:
            stats["consecutive_failures"] = 0
            spec = ScheduleSpec.from_dict(job.schedule or {})
            anti_ban_model = JobAntiBanModel(**(job.anti_ban or {}))
            if spec.kind.value == "manual":
                next_run = None
            else:
                candidate = compute_next_run(
                    spec, now, app_settings.anti_ban, anti_ban_model.aggressiveness, self._rng
                )
                next_run = (
                    clamp_to_active_hours(candidate, app_settings.schedule)
                    if candidate
                    else None
                )

        stats["total_runs"] = int(stats.get("total_runs", 0)) + 1
        job.stats = stats
        job.last_run_at = now
        job.next_run_at = next_run
        await session.flush()

        if outcome in _FAILURE_OUTCOMES:
            backoff = stats.get("last_backoff_minutes")
            message = (
                f"Job '{job.name}' rescheduled in {backoff} minutes "
                f"after failure ({outcome.value})"
            )
            await emit_event(
                session,
                type=EventType.RUN_BACKOFF,
                level=EventLevel.WARNING,
                category=EventCategory.RUN,
                message=message,
                params={"outcome": outcome.value, "backoff_minutes": backoff},
                job_id=job.id,
            )

    async def _apply_account_health(
        self,
        session: AsyncSession,
        account: XAccountRow,
        outcome: OutcomeKind,
        app_settings: AppSettings,
        now: datetime,
        items_new: int,
    ) -> None:
        streaks = await runs_repo.consecutive_auth_failures(session)
        streak = streaks.get(account.id, 0)
        if outcome == OutcomeKind.AUTH_EXPIRED:
            streak = max(0, streak - 1)

        decision = apply_outcome_to_account(
            outcome,
            now,
            app_settings.anti_ban,
            current_score=account.health_score,
            current_status=account.status,
            consecutive_auth_failures=streak,
        )

        previous_status = account.status
        await accounts_repo.apply_health_decision(
            session,
            account.id,
            decision,
            items_delta=items_new,
            run_failed=outcome in _FAILURE_OUTCOMES,
        )

        became_invalid = (
            decision.new_status == AccountStatus.INVALID
            and previous_status != AccountStatus.INVALID
        )
        if became_invalid:
            message = (
                f"Account '{account.label}' invalidated — X keeps forcing "
                "login; cookies must be re-uploaded"
            )
            await emit_event(
                session,
                type=EventType.ACCOUNT_INVALIDATED,
                level=EventLevel.ERROR,
                category=EventCategory.ACCOUNT,
                message=message,
                account_id=account.id,
            )
        elif outcome == OutcomeKind.RATE_LIMITED:
            await emit_event(
                session,
                type=EventType.ACCOUNT_COOLDOWN,
                level=EventLevel.WARNING,
                category=EventCategory.ACCOUNT,
                message=f"Account '{account.label}' cooled down after rate-limit signals from X",
                params={"health": decision.new_score},
                account_id=account.id,
            )

    async def _emit_finish_events(
        self,
        job_id: int,
        account_id: int,
        run_id: int,
        outcome: OutcomeKind,
        items_new: int,
        items_total: int,
        summary: dict[str, Any],
    ) -> None:
        level = (
            EventLevel.SUCCESS
            if outcome == OutcomeKind.SUCCESS
            else EventLevel.INFO
            if outcome == OutcomeKind.EMPTY
            else EventLevel.ERROR
        )
        async with self._sessions() as session:
            await emit_event(
                session,
                type=EventType.RUN_FINISHED,
                level=level,
                category=EventCategory.RUN,
                message=f"Run #{run_id} finished: {outcome.value} (+{items_new} new posts)",
                params={
                    "outcome": outcome.value,
                    "items_new": items_new,
                    "items_total": items_total,
                    "duration_ms": summary["duration_ms"],
                },
                job_id=job_id,
                account_id=account_id,
                run_id=run_id,
            )
            if items_new > 0:
                job = await jobs_repo.get_job(session, job_id)
                if job is not None:
                    await jobs_repo.bump_job_stats(
                        session, job_id, runs_delta=0, items_new_delta=items_new
                    )
                await emit_event(
                    session,
                    type=EventType.ITEMS_INGESTED,
                    level=EventLevel.SUCCESS,
                    category=EventCategory.DATA,
                    message=f"Ingested {items_new} new posts (run #{run_id})",
                    params={"items_new": items_new, "items_total": items_total},
                    job_id=job_id,
                    run_id=run_id,
                )
            await session.commit()

    # ------------------------------------------------------------------

    async def _skip_run(self, run_id: int, reason: str) -> None:
        now = datetime.now(tz=UTC)
        async with self._sessions() as session:
            run = await runs_repo.get_run(session, run_id)
            if run is not None and run.status == RunStatus.QUEUED:
                run.status = RunStatus.SKIPPED
                run.finished_at = now
                run.outcome = {"kind": OutcomeKind.SKIPPED.value, "message": reason}
                await session.commit()
        await emit_safe(
            EventType.RUN_FINISHED,
            EventLevel.WARNING,
            EventCategory.RUN,
            f"Run #{run_id} skipped: {reason}",
            params={"outcome": "skipped", "reason": reason},
            run_id=run_id,
        )


async def emit_safe(
    type: EventType,
    level: EventLevel,
    category: EventCategory,
    message: str,
    *,
    params: dict | None = None,
    account_id: int | None = None,
    job_id: int | None = None,
    run_id: int | None = None,
) -> None:
    """Emit an event with its own short-lived session (best-effort)."""
    from xfox.db.engine import get_session_factory

    try:
        async with get_session_factory()() as session:
            await emit_event(
                session,
                type=type,
                level=level,
                category=category,
                message=message,
                params=params,
                account_id=account_id,
                job_id=job_id,
                run_id=run_id,
            )
            await session.commit()
    except Exception:  # pragma: no cover - never let logging break a run
        from loguru import logger

        logger.exception("Failed to persist event {}", type.value)
