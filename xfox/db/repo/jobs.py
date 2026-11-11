"""Job repository."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import JobRow
from xfox.domain.enums import JobStatus


async def list_jobs(session: AsyncSession) -> list[JobRow]:
    result = await session.execute(select(JobRow).order_by(JobRow.id))
    return list(result.scalars().all())


async def get_job(session: AsyncSession, job_id: int) -> JobRow | None:
    return await session.get(JobRow, job_id)


async def create_job(
    session: AsyncSession,
    *,
    name: str,
    type: str,
    config: dict,
    schedule: dict,
    anti_ban: dict,
    account_id: int | None,
    priority: int,
    created_by: int | None,
) -> JobRow:
    row = JobRow(
        name=name,
        type=type,
        config=config,
        schedule=schedule,
        anti_ban=anti_ban,
        account_id=account_id,
        priority=priority,
        status=JobStatus.ACTIVE,
        stats={},
    )
    session.add(row)
    await session.flush()
    return row


async def update_job(session: AsyncSession, job: JobRow, **fields: object) -> JobRow:
    for key, value in fields.items():
        setattr(job, key, value)
    await session.flush()
    return job


async def delete_job(session: AsyncSession, job: JobRow) -> None:
    await session.delete(job)
    await session.flush()


async def due_jobs(session: AsyncSession, now: datetime) -> list[JobRow]:
    """Active jobs whose next_run_at has arrived — highest priority first."""
    stmt = (
        select(JobRow)
        .where(JobRow.status == JobStatus.ACTIVE)
        .where(JobRow.next_run_at.is_not(None))
        .where(JobRow.next_run_at <= now)
        .order_by(JobRow.priority.desc(), JobRow.next_run_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_run_scheduled(
    session: AsyncSession,
    job_id: int,
    *,
    last_run_at: datetime,
    next_run_at: datetime | None,
) -> None:
    job = await session.get(JobRow, job_id)
    if job is None:
        return
    job.last_run_at = last_run_at
    job.next_run_at = next_run_at
    await session.flush()


async def bump_job_stats(
    session: AsyncSession, job_id: int, *, runs_delta: int = 0, items_new_delta: int = 0
) -> None:
    job = await session.get(JobRow, job_id)
    if job is None:
        return
    stats = dict(job.stats or {})
    stats["total_runs"] = int(stats.get("total_runs", 0)) + runs_delta
    stats["items_new"] = int(stats.get("items_new", 0)) + items_new_delta
    job.stats = stats
    await session.flush()


async def set_status(session: AsyncSession, job_id: int, status: JobStatus) -> None:
    job = await session.get(JobRow, job_id)
    if job is not None:
        job.status = status
        await session.flush()
