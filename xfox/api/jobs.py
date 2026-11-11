"""Job & run endpoints — CRUD, actions (run now / pause / resume), history."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from xfox.api.deps import CurrentUser, DbDep, require
from xfox.config import settings as app_config
from xfox.db.models import XAccountRow
from xfox.db.repo import accounts as accounts_repo
from xfox.db.repo import jobs as jobs_repo
from xfox.db.repo import runs as runs_repo
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import (
    EventCategory,
    EventLevel,
    EventType,
    JobStatus,
    Permission,
)
from xfox.domain.policies import (
    ScheduleSpec,
    clamp_to_active_hours,
    compute_next_run,
)
from xfox.domain.schemas import (
    JobActionRequest,
    JobCreateRequest,
    JobPublic,
    JobUpdateRequest,
    MessageResponse,
    RunPage,
    RunPublic,
)
from xfox.engine.events import emit_event
from xfox.engine.orchestrator import get_engine

router = APIRouter(prefix="/api", tags=["jobs"])

ManagerUser = Annotated[XAccountRow, Depends(require(Permission.JOBS_MANAGE))]
ReaderUser = Annotated[Any, Depends(require(Permission.JOBS_READ))]

_rng = random.Random()


def _public(row) -> JobPublic:
    return JobPublic.model_validate(row)


def _run_public(row, job_name: str | None = None, account_label: str | None = None) -> RunPublic:
    payload = RunPublic.model_validate(row)
    payload.job_name = job_name
    payload.account_label = account_label
    return payload


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=list[JobPublic])
async def list_jobs(db: DbDep, _user: ReaderUser) -> list[JobPublic]:
    rows = await jobs_repo.list_jobs(db)
    return [_public(row) for row in rows]


@router.post("/jobs", response_model=JobPublic, status_code=status.HTTP_201_CREATED)
async def create_job(payload: JobCreateRequest, db: DbDep, user: CurrentUser) -> JobPublic:
    if not user or not _has_manage(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")

    if payload.account_id is not None:
        account = await accounts_repo.get_account(db, payload.account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")

    app_settings = await settings_repo.load_app_settings(db)
    spec = payload.schedule.to_spec()
    preset = payload.anti_ban.aggressiveness
    candidate = compute_next_run(spec, datetime.now(tz=UTC), app_settings.anti_ban, preset, _rng)
    next_run_at = clamp_to_active_hours(candidate, app_settings.schedule) if candidate else None

    row = await jobs_repo.create_job(
        db,
        name=payload.name,
        type=payload.type.value,
        config=payload.config.model_dump(exclude_none=True),
        schedule=payload.schedule.model_dump(exclude_none=True),
        anti_ban=payload.anti_ban.model_dump(),
        account_id=payload.account_id,
        priority=payload.priority,
        created_by=user.id,
    )
    row.next_run_at = next_run_at
    await db.flush()

    await emit_event(
        db,
        type=EventType.JOB_CREATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.JOB,
        message=f"Job '{row.name}' created ({row.type})",
        job_id=row.id,
    )
    await db.flush()
    return _public(row)


def _has_manage(user) -> bool:
    from xfox.domain.enums import Role
    from xfox.domain.permissions import role_has

    return role_has(Role(user.role), Permission.JOBS_MANAGE)


@router.get("/jobs/{job_id}", response_model=JobPublic)
async def get_job(job_id: int, db: DbDep, _user: ReaderUser) -> JobPublic:
    row = await jobs_repo.get_job(db, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    return _public(row)


@router.patch("/jobs/{job_id}", response_model=JobPublic)
async def update_job(
    job_id: int, payload: JobUpdateRequest, db: DbDep, _user: ManagerUser
) -> JobPublic:
    row = await jobs_repo.get_job(db, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")

    if payload.config is not None:
        row.config = payload.config.model_dump(exclude_none=True)
    if payload.schedule is not None:
        row.schedule = payload.schedule.model_dump(exclude_none=True)
    if payload.anti_ban is not None:
        row.anti_ban = payload.anti_ban.model_dump()
    if payload.name:
        row.name = payload.name
    if payload.priority is not None:
        row.priority = payload.priority
    if payload.account_id is not None:
        account = await accounts_repo.get_account(db, payload.account_id)
        if account is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
        row.account_id = payload.account_id
    elif payload.account_id is None and "account_id" in payload.model_fields_set:
        row.account_id = None

    # Recompute next run when the schedule changed and job is active.
    if payload.schedule is not None and row.status == JobStatus.ACTIVE:
        app_settings = await settings_repo.load_app_settings(db)
        spec = ScheduleSpec.from_dict(row.schedule)
        preset = (row.anti_ban or {}).get("aggressiveness", "balanced")
        candidate = compute_next_run(
            spec, datetime.now(tz=UTC), app_settings.anti_ban, preset, _rng
        )
        row.next_run_at = (
            clamp_to_active_hours(candidate, app_settings.schedule) if candidate else None
        )

    await emit_event(
        db,
        type=EventType.JOB_UPDATED,
        level=EventLevel.INFO,
        category=EventCategory.JOB,
        message=f"Job '{row.name}' updated",
        job_id=row.id,
    )
    await db.flush()
    return _public(row)


@router.delete("/jobs/{job_id}", response_model=MessageResponse)
async def delete_job(job_id: int, db: DbDep, _user: ManagerUser) -> MessageResponse:
    row = await jobs_repo.get_job(db, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    name = row.name
    await jobs_repo.delete_job(db, row)
    await emit_event(
        db,
        type=EventType.JOB_DELETED,
        level=EventLevel.WARNING,
        category=EventCategory.JOB,
        message=f"Job '{name}' deleted",
    )
    await db.flush()
    return MessageResponse(message="job_deleted")


@router.post("/jobs/{job_id}/action", response_model=MessageResponse)
async def job_action(
    job_id: int, payload: JobActionRequest, db: DbDep, user: CurrentUser
) -> MessageResponse:
    if not _has_manage(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")

    row = await jobs_repo.get_job(db, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")

    engine = get_engine()

    if payload.action == "run_now":
        if await runs_repo.has_active_run(db, row.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "run_already_active")
        run = await engine.trigger_job(row.id, triggered_by=user.id)
        run_number = run.id if run else "?"
        message = (
            f"Job '{row.name}' triggered manually by '{user.username}' (run #{run_number})"
        )
        await emit_event(
            db,
            type=EventType.JOB_TRIGGERED,
            level=EventLevel.INFO,
            category=EventCategory.JOB,
            message=message,
            job_id=row.id,
            run_id=run.id if run else None,
        )
        await db.flush()
        return MessageResponse(message="run_queued", details={"run_id": run.id if run else None})

    if payload.action == "pause":
        await jobs_repo.set_status(db, row.id, JobStatus.PAUSED)
        await emit_event(
            db,
            type=EventType.JOB_PAUSED,
            level=EventLevel.INFO,
            category=EventCategory.JOB,
            message=f"Job '{row.name}' paused",
            job_id=row.id,
        )
        await db.flush()
        return MessageResponse(message="job_paused")

    # resume
    await jobs_repo.set_status(db, row.id, JobStatus.ACTIVE)
    app_settings = await settings_repo.load_app_settings(db)
    spec = ScheduleSpec.from_dict(row.schedule or {})
    preset = (row.anti_ban or {}).get("aggressiveness", "balanced")
    candidate = compute_next_run(spec, datetime.now(tz=UTC), app_settings.anti_ban, preset, _rng)
    row.next_run_at = clamp_to_active_hours(candidate, app_settings.schedule) if candidate else None
    await emit_event(
        db,
        type=EventType.JOB_RESUMED,
        level=EventLevel.SUCCESS,
        category=EventCategory.JOB,
        message=f"Job '{row.name}' resumed",
        job_id=row.id,
    )
    await db.flush()
    engine.wake()
    return MessageResponse(message="job_resumed")


@router.get("/jobs/{job_id}/runs", response_model=RunPage)
async def job_runs(
    job_id: int,
    db: DbDep,
    _user: ReaderUser,
    page: int = 1,
    page_size: int = 20,
) -> RunPage:
    row = await jobs_repo.get_job(db, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    rows, total = await runs_repo.list_runs(db, job_id=job_id, page=page, page_size=page_size)
    account_labels = await _account_labels(db)
    return RunPage(
        items=[
            _run_public(r, job_name=row.name, account_label=account_labels.get(r.account_id))
            for r in rows
        ],
        total=total,
    )


# ---------------------------------------------------------------------------
# Runs (global)
# ---------------------------------------------------------------------------


@router.get("/runs", response_model=RunPage)
async def list_runs(
    db: DbDep,
    _user: ReaderUser,
    job_id: int | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> RunPage:
    rows, total = await runs_repo.list_runs(
        db, job_id=job_id, status=status_filter, page=page, page_size=page_size
    )
    job_names = await _job_names(db)
    account_labels = await _account_labels(db)
    return RunPage(
        items=[
            _run_public(
                r,
                job_name=job_names.get(r.job_id),
                account_label=account_labels.get(r.account_id),
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/runs/{run_id}", response_model=RunPublic)
async def get_run(run_id: int, db: DbDep, _user: ReaderUser) -> RunPublic:
    row = await runs_repo.get_run(db, run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run_not_found")
    job_names = await _job_names(db)
    account_labels = await _account_labels(db)
    return _run_public(
        row,
        job_name=job_names.get(row.job_id),
        account_label=account_labels.get(row.account_id),
    )


@router.post("/runs/{run_id}/cancel", response_model=MessageResponse)
async def cancel_run(run_id: int, db: DbDep, user: CurrentUser) -> MessageResponse:
    if not _has_manage(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")
    engine = get_engine()
    cancelled = await engine.cancel_run(run_id)
    if not cancelled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run_not_active")
    await emit_event(
        db,
        type=EventType.RUN_CANCELLED,
        level=EventLevel.WARNING,
        category=EventCategory.RUN,
        message=f"Run #{run_id} cancelled by '{user.username}'",
        run_id=run_id,
    )
    await db.flush()
    return MessageResponse(message="run_cancelled")


@router.get("/runs/{run_id}/log")
async def run_log(run_id: int, db: DbDep, _user: ReaderUser) -> dict:
    row = await runs_repo.get_run(db, run_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run_not_found")
    log_path = app_config.run_logs_dir / f"run-{run_id}.log"
    content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    return {"run_id": run_id, "content": content}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _job_names(db) -> dict[int, str]:
    return {row.id: row.name for row in await jobs_repo.list_jobs(db)}


async def _account_labels(db) -> dict[int, str]:
    return {row.id: row.label for row in await accounts_repo.list_accounts(db)}
