"""Event repository — the persisted audit log."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import EventRow


async def add_event(
    session: AsyncSession,
    *,
    type: str,
    level: str,
    category: str,
    message: str,
    params: dict | None = None,
    account_id: int | None = None,
    job_id: int | None = None,
    run_id: int | None = None,
) -> EventRow:
    row = EventRow(
        type=type,
        level=level,
        category=category,
        message=message,
        params=params,
        account_id=account_id,
        job_id=job_id,
        run_id=run_id,
    )
    session.add(row)
    await session.flush()
    return row


async def list_events(
    session: AsyncSession,
    *,
    level: str | None = None,
    category: str | None = None,
    q: str | None = None,
    account_id: int | None = None,
    job_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[EventRow], int]:
    stmt = select(EventRow)
    if level:
        stmt = stmt.where(EventRow.level == level)
    if category:
        stmt = stmt.where(EventRow.category == category)
    if account_id is not None:
        stmt = stmt.where(EventRow.account_id == account_id)
    if job_id is not None:
        stmt = stmt.where(EventRow.job_id == job_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(EventRow.message.ilike(pattern))

    total_result = await session.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = int(total_result.scalar_one())

    rows_result = await session.execute(
        stmt.order_by(EventRow.ts.desc(), EventRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows_result.scalars().all()), total


async def purge_events(session: AsyncSession, older_than_days: int) -> int:
    cutoff = datetime.now(tz=UTC) - timedelta(days=older_than_days)
    result = await session.execute(EventRow.__table__.delete().where(EventRow.ts < cutoff))
    return result.rowcount or 0
