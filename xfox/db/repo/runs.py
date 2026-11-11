"""Job-run repository — execution history and risk signals."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import JobRunRow
from xfox.domain.enums import OutcomeKind, RunStatus
from xfox.domain.policies import RunSignal


async def create_run(
    session: AsyncSession,
    *,
    job_id: int,
    account_id: int | None,
    triggered_by: int | None = None,
) -> JobRunRow:
    row = JobRunRow(
        job_id=job_id,
        account_id=account_id,
        status=RunStatus.QUEUED,
        triggered_by=triggered_by,
    )
    session.add(row)
    await session.flush()
    return row


async def update_run(session: AsyncSession, run_id: int, **fields: object) -> None:
    run = await session.get(JobRunRow, run_id)
    if run is not None:
        for key, value in fields.items():
            setattr(run, key, value)
        await session.flush()


async def get_run(session: AsyncSession, run_id: int) -> JobRunRow | None:
    return await session.get(JobRunRow, run_id)


async def list_runs(
    session: AsyncSession,
    *,
    job_id: int | None = None,
    account_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[JobRunRow], int]:
    stmt = select(JobRunRow)
    if job_id is not None:
        stmt = stmt.where(JobRunRow.job_id == job_id)
    if account_id is not None:
        stmt = stmt.where(JobRunRow.account_id == account_id)
    if status:
        stmt = stmt.where(JobRunRow.status == status)

    total_result = await session.execute(select(func.count()).select_from(stmt.subquery()))
    total = int(total_result.scalar_one())

    rows_result = await session.execute(
        stmt.order_by(JobRunRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows_result.scalars().all()), total


async def recent_runs(session: AsyncSession, limit: int = 10) -> list[JobRunRow]:
    result = await session.execute(
        select(JobRunRow).order_by(JobRunRow.id.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def has_active_run(session: AsyncSession, job_id: int) -> bool:
    """True when the job already has a QUEUED or RUNNING run."""
    from sqlalchemy import func

    result = await session.execute(
        select(func.count())
        .select_from(JobRunRow)
        .where(
            JobRunRow.job_id == job_id,
            JobRunRow.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
        )
    )
    return int(result.scalar_one()) > 0


async def queued_runs(session: AsyncSession, limit: int = 10) -> list[JobRunRow]:
    """QUEUED runs in FIFO order, ready for execution."""
    result = await session.execute(
        select(JobRunRow)
        .where(JobRunRow.status == RunStatus.QUEUED)
        .order_by(JobRunRow.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def running_run_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(
        select(JobRunRow.id).where(JobRunRow.status == RunStatus.RUNNING)
    )
    return [int(row) for row in result.all()]


async def runs_today_by_account(session: AsyncSession) -> dict[int, int]:
    """Run counts per account since the start of the current UTC day."""
    day_start = datetime.now(tz=UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    stmt = (
        select(JobRunRow.account_id, func.count())
        .where(JobRunRow.account_id.is_not(None))
        .where(JobRunRow.created_at >= day_start)
        .group_by(JobRunRow.account_id)
    )
    result = await session.execute(stmt)
    return {int(account_id): int(count) for account_id, count in result.all()}


async def today_totals(session: AsyncSession) -> tuple[int, int, int]:
    """(runs, successful_runs, items_new) since the start of the current UTC day."""
    day_start = datetime.now(tz=UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    stmt = (
        select(
            JobRunRow.status,
            func.count().label("runs"),
            func.coalesce(func.sum(JobRunRow.items_new), 0).label("items"),
        )
        .where(JobRunRow.created_at >= day_start)
        .group_by(JobRunRow.status)
    )
    result = await session.execute(stmt)
    runs = successful = items = 0
    for status, status_runs, status_items in result.all():
        runs += int(status_runs)
        items += int(status_items)
        if status == RunStatus.SUCCESS:
            successful += int(status_runs)
    return runs, successful, items


async def recent_outcome_signals(
    session: AsyncSession, window_minutes: int
) -> list[RunSignal]:
    """Finished-run outcomes inside the risk window, feeding :func:`evaluate_risk`."""
    cutoff = datetime.now(tz=UTC) - timedelta(minutes=window_minutes)
    stmt = select(JobRunRow.finished_at, JobRunRow.outcome).where(
        JobRunRow.finished_at.is_not(None), JobRunRow.finished_at >= cutoff
    )
    result = await session.execute(stmt)
    signals: list[RunSignal] = []
    for finished_at, outcome in result.all():
        if not outcome or "kind" not in outcome:
            continue
        signals.append(RunSignal(OutcomeKind(outcome["kind"]), finished_at))
    return signals


async def consecutive_auth_failures(session: AsyncSession) -> dict[int, int]:
    """Per-account streaks of consecutive AUTH_EXPIRED outcomes (newest-first scan)."""
    stmt = (
        select(JobRunRow.account_id, JobRunRow.outcome)
        .where(JobRunRow.account_id.is_not(None))
        .order_by(JobRunRow.id.desc())
        .limit(500)
    )
    result = await session.execute(stmt)
    streaks: dict[int, int] = {}
    for account_id, outcome in result.all():
        kind = (outcome or {}).get("kind")
        if kind == OutcomeKind.AUTH_EXPIRED:
            streaks[int(account_id)] = streaks.get(int(account_id), 0) + 1
        else:
            streaks.setdefault(int(account_id), 0)
    return streaks


async def purge_finished_runs(session: AsyncSession, older_than_days: int) -> int:
    cutoff = datetime.now(tz=UTC) - timedelta(days=older_than_days)
    finished = [
        RunStatus.SUCCESS,
        RunStatus.EMPTY,
        RunStatus.FAILED,
        RunStatus.TIMEOUT,
        RunStatus.CANCELLED,
    ]
    stmt = JobRunRow.__table__.delete().where(
        JobRunRow.finished_at.is_not(None),
        JobRunRow.finished_at < cutoff,
        JobRunRow.status.in_([s.value for s in finished]),
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
