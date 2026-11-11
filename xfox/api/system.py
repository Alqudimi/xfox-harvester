"""System endpoints — dashboard overview, health status, risk control, maintenance."""

from __future__ import annotations

import shutil
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from xfox import __version__
from xfox.api.deps import DbDep, require
from xfox.config import settings as app_config
from xfox.db.models import XAccountRow
from xfox.db.repo import accounts as accounts_repo
from xfox.db.repo import authors as authors_repo
from xfox.db.repo import events as events_repo
from xfox.db.repo import jobs as jobs_repo
from xfox.db.repo import posts as posts_repo
from xfox.db.repo import runs as runs_repo
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import (
    AccountStatus,
    EventCategory,
    EventLevel,
    EventType,
    Permission,
)
from xfox.domain.schemas import (
    AuthorPublic,
    DailyCount,
    MessageResponse,
    OverviewResponse,
    OverviewToday,
    OverviewTotals,
    RiskState,
    RunPublic,
    SystemStatusResponse,
)
from xfox.engine.events import emit_event
from xfox.engine.orchestrator import get_engine
from xfox.engine.xcrawlfox import XCrawlFoxAdapter

router = APIRouter(prefix="/api/system", tags=["system"])

ReaderUser = Annotated[Any, Depends(require(Permission.SYSTEM_READ))]
ManagerUser = Annotated[XAccountRow, Depends(require(Permission.SYSTEM_MANAGE))]

_STARTED_AT = time.monotonic()


@router.get("/overview", response_model=OverviewResponse)
async def overview(db: DbDep, _user: ReaderUser) -> OverviewResponse:
    engine = get_engine()
    accounts = await accounts_repo.list_accounts(db)
    jobs = await jobs_repo.list_jobs(db)
    runs_today, successful_today, items_today = await runs_repo.today_totals(db)

    risk_snapshot = engine.risk.snapshot()
    top_rows = await authors_repo.top_authors(db, limit=8)
    daily = await posts_repo.daily_counts(db, days=14)
    recent_run_rows = await runs_repo.recent_runs(db, limit=8)

    job_names = {job.id: job.name for job in jobs}
    account_labels = {account.id: account.label for account in accounts}

    recent_runs = []
    for row in recent_run_rows:
        payload = RunPublic.model_validate(row)
        payload.job_name = job_names.get(row.job_id)
        payload.account_label = account_labels.get(row.account_id)
        recent_runs.append(payload)

    return OverviewResponse(
        totals=OverviewTotals(
            posts=await posts_repo.count_posts(db),
            authors=await authors_repo.count_authors(db),
            accounts_total=len(accounts),
            accounts_active=sum(1 for a in accounts if a.status == AccountStatus.ACTIVE),
            accounts_invalid=sum(1 for a in accounts if a.status == AccountStatus.INVALID),
            jobs_total=len(jobs),
            jobs_active=sum(1 for j in jobs if j.status == "active"),
        ),
        today=OverviewToday(
            runs=runs_today, successful_runs=successful_today, items_new=items_today
        ),
        risk=RiskState(
            level=risk_snapshot["level"],
            reasons=risk_snapshot["reasons"],
            paused=risk_snapshot["paused"],
            paused_since=risk_snapshot["paused_since"],
            auto_resume_at=risk_snapshot["auto_resume_at"],
        ),
        engine_running=engine.status_snapshot()["running"],
        collection_14d=[DailyCount(date=entry["date"], count=entry["count"]) for entry in daily],
        top_authors=[
            AuthorPublic(
                username=row["username"],
                nickname=row["nickname"],
                avatar_url=row["avatar_url"],
                profile_url=row["profile_url"],
                posts_count=int(row["posts_count"]),
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
            )
            for row in top_rows
        ],
        recent_runs=recent_runs,
    )


@router.get("/status", response_model=SystemStatusResponse)
async def system_status(db: DbDep, _user: ReaderUser) -> SystemStatusResponse:
    engine = get_engine()

    database_ok = True
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
    except Exception:
        database_ok = False

    disk_free_gb = None
    try:
        usage = shutil.disk_usage(app_config.data_dir)
        disk_free_gb = round(usage.free / 1024**3, 2)
    except Exception:
        pass

    risk_snapshot = engine.risk.snapshot()
    return SystemStatusResponse(
        version=__version__,
        environment=app_config.environment,
        crawlfox_bin=app_config.crawlfox_bin,
        crawlfox_available=XCrawlFoxAdapter.binary_available(),
        camoufox_fetched=XCrawlFoxAdapter.camoufox_fetched(),
        database_ok=database_ok,
        data_dir=str(app_config.data_dir.resolve()),
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 1),
        active_runs=engine.status_snapshot()["active_runs"],
        risk=RiskState(
            level=risk_snapshot["level"],
            reasons=risk_snapshot["reasons"],
            paused=risk_snapshot["paused"],
            paused_since=risk_snapshot["paused_since"],
            auto_resume_at=risk_snapshot["auto_resume_at"],
        ),
        disk_free_gb=disk_free_gb,
    )


@router.post("/risk/acknowledge", response_model=MessageResponse)
async def acknowledge_risk(db: DbDep, _user: ManagerUser) -> MessageResponse:
    engine = get_engine()
    await engine.acknowledge_risk()
    return MessageResponse(message="engine_resumed")


class PurgeRequest(BaseModel):
    confirm: str


@router.post("/maintenance/purge", response_model=MessageResponse)
async def run_maintenance(db: DbDep, _user: ManagerUser) -> MessageResponse:
    """Apply retention policies: delete old events and finished runs."""
    app_settings = await settings_repo.load_app_settings(db)
    events_removed = await events_repo.purge_events(db, app_settings.retention.events_days)
    runs_removed = await runs_repo.purge_finished_runs(
        db, app_settings.retention.finished_runs_days
    )
    await emit_event(
        db,
        type=EventType.MAINTENANCE_PURGE,
        level=EventLevel.INFO,
        category=EventCategory.SYSTEM,
        message=f"Maintenance: purged {events_removed} events and {runs_removed} old runs",
        params={"events_removed": events_removed, "runs_removed": runs_removed},
    )
    await db.flush()
    return MessageResponse(
        message="maintenance_done",
        details={"events_removed": events_removed, "runs_removed": runs_removed},
    )


@router.delete("/data/posts", response_model=MessageResponse)
async def purge_all_posts(
    db: DbDep, _user: ManagerUser, confirm: PurgeRequest | None = None
) -> MessageResponse:
    """Danger zone: delete every harvested post and author (workspaces untouched)."""
    if confirm is None or confirm.confirm != "DELETE":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirmation_required")

    from sqlalchemy import text

    await db.execute(text("DELETE FROM posts"))
    await db.execute(text("DELETE FROM authors"))
    await emit_event(
        db,
        type=EventType.DATA_PURGED,
        level=EventLevel.WARNING,
        category=EventCategory.DATA,
        message="All harvested posts and authors purged by an administrator",
    )
    await db.flush()
    return MessageResponse(message="data_purged")
