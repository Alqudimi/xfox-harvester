"""Engine orchestrator — the supervisor loop.

Responsibilities:
    * keep the global risk gauge fresh and honor RED pauses (manual/auto resume),
    * turn due jobs into QUEUED runs and compute their next occurrence,
    * launch QUEUED runs while respecting concurrency, global pacing, active
      hours and account eligibility,
    * provide the control surface used by the API (trigger, cancel, pause, resume).

The loop runs every few seconds inside the FastAPI lifespan; a wake-up event
lets API actions (e.g. "run now") take effect immediately.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xfox.db.engine import get_session_factory
from xfox.db.models import JobRunRow
from xfox.db.repo import jobs as jobs_repo
from xfox.db.repo import runs as runs_repo
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import (
    EventCategory,
    EventLevel,
    EventType,
    RunStatus,
)
from xfox.domain.policies import (
    AppSettings,
    ScheduleSpec,
    clamp_to_active_hours,
    compute_next_run,
    within_active_hours,
)
from xfox.domain.schemas import JobAntiBanModel
from xfox.engine.accounts import AccountPool
from xfox.engine.events import emit_event
from xfox.engine.risk import RiskMonitor
from xfox.engine.runner import JobRunner

_TICK_SECONDS = 5.0


class Engine:
    """Process-wide harvesting supervisor (single instance)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sessions = session_factory or get_session_factory()
        self.pool = AccountPool()
        self.risk = RiskMonitor()
        self.runner = JobRunner(self._sessions)
        self.app_settings = AppSettings()

        self.active: dict[int, asyncio.Task[None]] = {}
        self.last_start: datetime | None = None
        self.started_at: datetime | None = None

        self._loop_task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._stopped = asyncio.Event()
        self._rng = random.Random()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the supervisor loop (idempotent)."""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stopped.clear()
        self.started_at = datetime.now(tz=UTC)
        self._loop_task = asyncio.create_task(self._loop(), name="xfox-engine-loop")
        logger.info("Harvesting engine started")

    async def stop(self) -> None:
        """Graceful shutdown: stop scheduling, cancel runs, kill subprocesses."""
        self._stopped.set()
        self._wake.set()
        if self._loop_task is not None:
            try:
                await asyncio.wait_for(self._loop_task, timeout=10)
            except (TimeoutError, asyncio.CancelledError):
                self._loop_task.cancel()
            self._loop_task = None

        for task in list(self.active.values()):
            task.cancel()
        for task in list(self.active.values()):
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=15)
        self.active.clear()
        logger.info("Harvesting engine stopped")

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Engine tick failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=_TICK_SECONDS)
            self._wake.clear()

    def wake(self) -> None:
        """Interrupt the sleep so a just-queued run starts immediately."""
        self._wake.set()

    # ------------------------------------------------------------------
    # Tick: risk → schedule → execute
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        now = datetime.now(tz=UTC)
        async with self._sessions() as session:
            self.app_settings = await settings_repo.load_app_settings(session)
            await self._refresh_risk(session)

            if self.risk.paused:
                if self.risk.maybe_auto_resume():
                    await emit_event(
                        session,
                        type=EventType.ENGINE_RESUMED,
                        level=EventLevel.SUCCESS,
                        category=EventCategory.RISK,
                        message="Engine auto-resumed after RED cooldown",
                    )
                    await session.commit()
                else:
                    await session.commit()
                    return

            await self._schedule_due_jobs(session, now)
            launched = await self._launch_queued_runs(session, now)
            if launched:
                await session.commit()
            else:
                await session.commit()

    async def _refresh_risk(self, session: AsyncSession) -> None:
        signals = await runs_repo.recent_outcome_signals(
            session, self.app_settings.risk.window_minutes
        )
        changed, assessment = self.risk.refresh(signals, self.app_settings.risk)
        if not changed:
            return

        await emit_event(
            session,
            type=EventType.RISK_LEVEL_CHANGED,
            level=EventLevel.WARNING if assessment.level != "green" else EventLevel.INFO,
            category=EventCategory.RISK,
            message=f"Risk level changed to {assessment.level.value.upper()}"
            + (f" ({', '.join(assessment.reasons)})" if assessment.reasons else ""),
            params={"level": assessment.level.value, "reasons": assessment.reasons},
        )
        if self.risk.paused:
            await emit_event(
                session,
                type=EventType.ENGINE_PAUSED,
                level=EventLevel.ERROR,
                category=EventCategory.RISK,
                message="Engine PAUSED — risk level RED. All scheduled harvesting halted.",
                params={"reasons": assessment.reasons},
            )

    async def _schedule_due_jobs(self, session: AsyncSession, now: datetime) -> None:
        """Create a QUEUED run for every due job and push its next occurrence."""
        for job in await jobs_repo.due_jobs(session, now):
            if await runs_repo.has_active_run(session, job.id):
                # A previous run is still queued/running — do not pile up.
                spec = ScheduleSpec.from_dict(job.schedule or {})
                preset = JobAntiBanModel(**(job.anti_ban or {})).aggressiveness
                candidate = compute_next_run(
                    spec, now, self.app_settings.anti_ban, preset, self._rng, job.last_run_at
                )
                job.next_run_at = (
                    clamp_to_active_hours(candidate, self.app_settings.schedule)
                    if candidate
                    else now + timedelta(minutes=15)
                )
                continue

            await runs_repo.create_run(session, job_id=job.id, account_id=job.account_id)

            spec = ScheduleSpec.from_dict(job.schedule or {})
            preset = JobAntiBanModel(**(job.anti_ban or {})).aggressiveness
            candidate = compute_next_run(
                spec, now, self.app_settings.anti_ban, preset, self._rng, job.last_run_at
            )
            next_at = (
                clamp_to_active_hours(candidate, self.app_settings.schedule) if candidate else None
            )
            await jobs_repo.mark_run_scheduled(
                session, job.id, last_run_at=now, next_run_at=next_at
            )
            logger.debug("Job '{}' #{} scheduled, next run at {}", job.name, job.id, next_at)

    async def _launch_queued_runs(self, session: AsyncSession, now: datetime) -> bool:
        """Start QUEUED runs while every gate allows it. Returns True if any started."""
        anti_ban = self.app_settings.anti_ban
        capacity = anti_ban.max_concurrent_runs - len(self.active)
        if capacity <= 0:
            return False

        # Global pacing: minimum spacing between run *starts* ( YELLOW doubles it ).
        yellow = self.risk.level.value == "yellow"
        gap_minutes = anti_ban.global_min_gap_minutes * (2 if yellow else 1)
        if self.last_start is not None:
            elapsed = now - self.last_start
            if elapsed < timedelta(minutes=gap_minutes * 0.9):
                return False

        # Active-hours gate (server local time).
        if not within_active_hours(datetime.now().astimezone(), self.app_settings.schedule):
            return False

        launched = False
        for run in await runs_repo.queued_runs(session, limit=capacity):
            account, reason = await self.pool.select(
                session,
                anti_ban,
                pinned_account_id=run.account_id,
            )
            if account is None:
                if run.triggered_by is not None:
                    # Manual triggers deserve explicit feedback instead of an
                    # endless QUEUED state.
                    await self._skip_run_row(session, run, reason or "no_eligible_account")
                continue

            if run.account_id is None:
                run.account_id = account.id
                await session.flush()

            task = asyncio.create_task(
                self._execute_run(run.id), name=f"xfox-run-{run.id}"
            )
            self.active[run.id] = task
            self.last_start = now
            launched = True
        return launched

    async def _execute_run(self, run_id: int) -> None:
        try:
            await self.runner.execute(run_id)
        except asyncio.CancelledError:
            logger.info("Run {} cancelled", run_id)
        except Exception:
            logger.exception("Run {} crashed", run_id)
        finally:
            self.active.pop(run_id, None)

    async def _skip_run_row(self, session: AsyncSession, run: JobRunRow, reason: str) -> None:
        run.status = RunStatus.SKIPPED
        run.finished_at = datetime.now(tz=UTC)
        run.outcome = {"kind": "skipped", "message": reason}
        await session.flush()
        await emit_event(
            session,
            type=EventType.RUN_FINISHED,
            level=EventLevel.WARNING,
            category=EventCategory.RUN,
            message=f"Run #{run.id} skipped: {reason}",
            params={"outcome": "skipped", "reason": reason},
            run_id=run.id,
        )

    # ------------------------------------------------------------------
    # Control surface (used by the API layer)
    # ------------------------------------------------------------------

    async def trigger_job(self, job_id: int, triggered_by: int) -> JobRunRow | None:
        """Queue an immediate run of *job_id* (skips schedule waiting)."""
        async with self._sessions() as session:
            job = await jobs_repo.get_job(session, job_id)
            if job is None:
                return None
            run = await runs_repo.create_run(
                session,
                job_id=job.id,
                account_id=job.account_id,
                triggered_by=triggered_by,
            )
            await session.commit()
        self.wake()
        return run

    async def cancel_run(self, run_id: int) -> bool:
        """Cancel a RUNNING (kills the browser) or QUEUED run."""
        task = self.active.get(run_id)
        if task is not None:
            task.cancel()
            return True
        async with self._sessions() as session:
            run = await runs_repo.get_run(session, run_id)
            if run is not None and run.status == RunStatus.QUEUED:
                run.status = RunStatus.CANCELLED
                run.finished_at = datetime.now(tz=UTC)
                run.outcome = {"kind": "cancelled", "message": "cancelled_by_user"}
                await session.commit()
                return True
            if run is not None and run.status == RunStatus.RUNNING:
                # Orphaned RUNNING row (e.g. server restarted mid-run): finalize it.
                run.status = RunStatus.CANCELLED
                run.finished_at = datetime.now(tz=UTC)
                run.outcome = {"kind": "cancelled", "message": "orphaned_after_restart"}
                await session.commit()
                return True
        return False

    async def acknowledge_risk(self) -> None:
        """Manual resume after a RED pause."""
        async with self._sessions() as session:
            self.risk.resume()
            await emit_event(
                session,
                type=EventType.ENGINE_RESUMED,
                level=EventLevel.SUCCESS,
                category=EventCategory.RISK,
                message="Engine resumed manually — risk window reset to GREEN",
            )
            await session.commit()
        self.wake()

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "running": self._loop_task is not None and not self._loop_task.done(),
            "active_runs": len(self.active),
            "risk": self.risk.snapshot(),
            "started_at": self.started_at,
        }

    async def reap_orphans(self) -> int:
        """Finalize RUNNING rows left behind by a restart (no live task)."""
        count = 0
        async with self._sessions() as session:
            for run_id in await runs_repo.running_run_ids(session):
                if run_id in self.active:
                    continue
                run = await runs_repo.get_run(session, run_id)
                if run is not None:
                    run.status = RunStatus.FAILED
                    run.finished_at = datetime.now(tz=UTC)
                    run.outcome = {"kind": "unknown_error", "message": "orphaned_after_restart"}
                    count += 1
            await session.commit()
        return count


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return (and lazily create) the global engine instance."""
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def reset_engine() -> None:
    """Test helper: drop the singleton."""
    global _engine
    _engine = None
