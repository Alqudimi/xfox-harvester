"""X-account endpoints — CRUD, cookie installation, and live account testing."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from xfox.api.deps import DbDep, require
from xfox.db.models import XAccountRow
from xfox.db.repo import accounts as accounts_repo
from xfox.db.repo import proxies as proxies_repo
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import (
    AccountStatus,
    EventCategory,
    EventLevel,
    EventType,
    JobType,
    Permission,
)
from xfox.domain.schemas import (
    CookieUploadRequest,
    MessageResponse,
    XAccountCreateRequest,
    XAccountPublic,
    XAccountUpdateRequest,
)
from xfox.engine.events import emit_event
from xfox.engine.workspaces import CookieValidationError, WorkspaceManager
from xfox.engine.xcrawlfox import XCrawlFoxAdapter

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

ManagerUser = Annotated[XAccountRow, Depends(require(Permission.ACCOUNTS_MANAGE))]
_workspaces = WorkspaceManager()


class CookieUploadResponse(BaseModel):
    message: str
    format: str
    cookie_count: int


class AccountTestResponse(BaseModel):
    outcome: str
    message: str | None = None
    collected: int = 0
    duration_ms: int = 0


def _public(row: XAccountRow) -> XAccountPublic:
    return XAccountPublic(
        id=row.id,
        label=row.label,
        notes=row.notes,
        status=row.status,
        health_score=row.health_score,
        proxy_id=row.proxy_id,
        stats={
            "total_runs": (row.stats or {}).get("total_runs", 0),
            "successful_runs": (row.stats or {}).get("successful_runs", 0),
            "failed_runs": (row.stats or {}).get("failed_runs", 0),
            "items_collected": (row.stats or {}).get("items_collected", 0),
        },
        has_cookies=_workspaces.has_cookies(row.id),
        cookie_updated_at=row.cookie_updated_at,
        last_run_at=row.last_run_at,
        cooldown_until=row.cooldown_until,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[XAccountPublic])
async def list_accounts(
    db: DbDep, _user: Annotated[Any, Depends(require(Permission.ACCOUNTS_READ))]
) -> list[XAccountPublic]:
    rows = await accounts_repo.list_accounts(db)
    return [_public(row) for row in rows]


@router.post("", response_model=XAccountPublic, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: XAccountCreateRequest, db: DbDep, _user: ManagerUser
) -> XAccountPublic:
    for row in await accounts_repo.list_accounts(db):
        if row.label == payload.label:
            raise HTTPException(status.HTTP_409_CONFLICT, "label_taken")

    if payload.proxy_id is not None and await proxies_repo.get_proxy(db, payload.proxy_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proxy_not_found")

    row = await accounts_repo.create_account(
        db, label=payload.label, notes=payload.notes, proxy_id=payload.proxy_id
    )
    _workspaces.ensure(row.id)
    await emit_event(
        db,
        type=EventType.ACCOUNT_CREATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.ACCOUNT,
        message=f"X account '{row.label}' added",
        account_id=row.id,
    )
    await db.flush()
    return _public(row)


@router.patch("/{account_id}", response_model=XAccountPublic)
async def update_account(
    account_id: int, payload: XAccountUpdateRequest, db: DbDep, _user: ManagerUser
) -> XAccountPublic:
    row = await accounts_repo.get_account(db, account_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")

    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        new_status = AccountStatus(updates.pop("status"))
        row.status = new_status.value
        if new_status == AccountStatus.ACTIVE and row.cooldown_until:
            row.cooldown_until = None
    if "proxy_id" in updates:
        proxy_id = updates.pop("proxy_id")
        if proxy_id is not None and await proxies_repo.get_proxy(db, proxy_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "proxy_not_found")
        row.proxy_id = proxy_id
    if "label" in updates and updates["label"]:
        row.label = updates.pop("label")
    if "notes" in updates:
        row.notes = updates.pop("notes")

    await emit_event(
        db,
        type=EventType.ACCOUNT_UPDATED,
        level=EventLevel.INFO,
        category=EventCategory.ACCOUNT,
        message=f"Account '{row.label}' updated (status={row.status})",
        account_id=row.id,
    )
    await db.flush()
    return _public(row)


@router.delete("/{account_id}", response_model=MessageResponse)
async def delete_account(account_id: int, db: DbDep, _user: ManagerUser) -> MessageResponse:
    row = await accounts_repo.get_account(db, account_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    label = row.label
    await accounts_repo.delete_account(db, row)
    _workspaces.remove(account_id)
    await emit_event(
        db,
        type=EventType.ACCOUNT_DELETED,
        level=EventLevel.WARNING,
        category=EventCategory.ACCOUNT,
        message=f"Account '{label}' deleted (workspace removed)",
    )
    await db.flush()
    return MessageResponse(message="account_deleted")


@router.post("/{account_id}/cookies", response_model=CookieUploadResponse)
async def upload_cookies(
    account_id: int, payload: CookieUploadRequest, db: DbDep, _user: ManagerUser
) -> CookieUploadResponse:
    row = await accounts_repo.get_account(db, account_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")

    try:
        report = _workspaces.install_cookies(account_id, payload.content)
    except CookieValidationError as exc:
        await emit_event(
            db,
            type=EventType.COOKIES_REJECTED,
            level=EventLevel.WARNING,
            category=EventCategory.ACCOUNT,
            message=f"Cookie upload for '{row.label}' rejected: {exc}",
            account_id=account_id,
        )
        await db.flush()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await accounts_repo.mark_cookies(db, account_id, present=True)
    cookie_count = len(report["cookies"])
    message = (
        f"Cookies installed for '{row.label}' "
        f"({cookie_count} cookies, {report['format']} format)"
    )
    await emit_event(
        db,
        type=EventType.COOKIES_UPDATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.ACCOUNT,
        message=message,
        account_id=account_id,
    )
    await db.flush()
    return CookieUploadResponse(
        message="cookies_installed",
        format=report["format"],
        cookie_count=len(report["cookies"]),
    )


@router.post("/{account_id}/test", response_model=AccountTestResponse)
async def test_account(account_id: int, db: DbDep, _user: ManagerUser) -> AccountTestResponse:
    """Run a minimal real harvest (1 post from @x) to verify the session works."""
    row = await accounts_repo.get_account(db, account_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account_not_found")
    if not _workspaces.has_cookies(account_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_cookies_installed")

    app_settings = await settings_repo.load_app_settings(db)
    adapter = XCrawlFoxAdapter()
    _workspaces.ensure(account_id)
    _workspaces.clean_output(account_id)

    config = adapter.build_crawl_config(
        JobType.MONITOR,
        {"monitor": {"users": [{"username": "x", "only_new": False, "max_tweets": 1}]}},
        app_settings.crawler,
    )
    config_path = _workspaces.write_crawl_config(account_id, config)

    from xfox.engine.outcomes import analyze_log

    result = await adapter.execute(
        account_id=account_id,
        config_path=config_path,
        headless=app_settings.crawler.headless,
        proxy_url=row.proxy.url if row.proxy and row.proxy.status == "active" else None,
        timeout_minutes=5,
        on_log=None,
    )
    items = _workspaces.read_output_items(account_id)
    analysis = analyze_log(result.log_text, items_collected=len(items))

    await emit_event(
        db,
        type=EventType.ACCOUNT_TESTED,
        level=EventLevel.SUCCESS if analysis.outcome.value == "success" else EventLevel.WARNING,
        category=EventCategory.ACCOUNT,
        message=f"Account '{row.label}' test: {analysis.outcome.value}"
        + (f" — {analysis.message}" if analysis.message else ""),
        params={"outcome": analysis.outcome.value, "signals": analysis.signals},
        account_id=account_id,
    )
    await db.flush()
    return AccountTestResponse(
        outcome=analysis.outcome.value,
        message=analysis.message,
        collected=len(items),
        duration_ms=result.duration_ms,
    )
