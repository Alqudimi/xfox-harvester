"""X-account repository (one row per harvested-account workspace)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from xfox.db.models import XAccountRow
from xfox.domain.enums import AccountStatus
from xfox.domain.policies import AccountRuntime, HealthDecision


async def list_accounts(session: AsyncSession) -> list[XAccountRow]:
    result = await session.execute(
        select(XAccountRow).options(selectinload(XAccountRow.proxy)).order_by(XAccountRow.id)
    )
    return list(result.scalars().all())


async def get_account(session: AsyncSession, account_id: int) -> XAccountRow | None:
    result = await session.execute(
        select(XAccountRow)
        .options(selectinload(XAccountRow.proxy))
        .where(XAccountRow.id == account_id)
    )
    return result.scalar_one_or_none()


async def create_account(
    session: AsyncSession, *, label: str, notes: str | None = None, proxy_id: int | None = None
) -> XAccountRow:
    row = XAccountRow(
        label=label,
        notes=notes,
        proxy_id=proxy_id,
        status=AccountStatus.ACTIVE,
        health_score=100,
        stats={},
    )
    session.add(row)
    await session.flush()
    return row


async def update_account(
    session: AsyncSession, account: XAccountRow, **fields: object
) -> XAccountRow:
    for key, value in fields.items():
        setattr(account, key, value)
    await session.flush()
    return account


async def delete_account(session: AsyncSession, account: XAccountRow) -> None:
    await session.delete(account)
    await session.flush()


async def mark_cookies(session: AsyncSession, account_id: int, present: bool) -> None:
    account = await session.get(XAccountRow, account_id)
    if account is not None:
        account.has_cookies = present
        account.cookie_updated_at = datetime.now(tz=UTC) if present else None
        if present and account.status == AccountStatus.INVALID:
            account.status = AccountStatus.ACTIVE
        await session.flush()


async def apply_health_decision(
    session: AsyncSession,
    account_id: int,
    decision: HealthDecision,
    *,
    items_delta: int = 0,
    run_failed: bool = False,
) -> None:
    """Persist the outcome of :func:`apply_outcome_to_account` plus stat bumps."""
    account = await session.get(XAccountRow, account_id)
    if account is None:
        return
    now = datetime.now(tz=UTC)
    stats = dict(account.stats or {})
    stats["total_runs"] = int(stats.get("total_runs", 0)) + 1
    if run_failed:
        stats["failed_runs"] = int(stats.get("failed_runs", 0)) + 1
    else:
        stats["successful_runs"] = int(stats.get("successful_runs", 0)) + 1
    stats["items_collected"] = int(stats.get("items_collected", 0)) + items_delta

    account.health_score = decision.new_score
    account.status = decision.new_status
    account.cooldown_until = decision.cooldown_until
    account.last_run_at = now
    account.stats = stats
    await session.flush()


async def runtime_snapshots(
    session: AsyncSession,
    runs_today_by_account: dict[int, int],
    auth_streaks: dict[int, int],
) -> list[AccountRuntime]:
    """Build policy-ready snapshots for every account."""
    rows = await list_accounts(session)
    return [
        AccountRuntime(
            account_id=row.id,
            status=AccountStatus(row.status),
            health_score=row.health_score,
            cooldown_until=row.cooldown_until,
            last_run_at=row.last_run_at,
            runs_today=runs_today_by_account.get(row.id, 0),
            total_runs=int((row.stats or {}).get("total_runs", 0)),
            consecutive_auth_failures=auth_streaks.get(row.id, 0),
        )
        for row in rows
    ]
