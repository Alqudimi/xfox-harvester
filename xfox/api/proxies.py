"""Proxy endpoints — CRUD and live connectivity checks."""

from __future__ import annotations

import time
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from xfox.api.deps import DbDep, require
from xfox.db.models import XAccountRow
from xfox.db.repo import proxies as proxies_repo
from xfox.domain.enums import EventCategory, EventLevel, EventType, Permission
from xfox.domain.schemas import (
    MessageResponse,
    ProxyCreateRequest,
    ProxyPublic,
    ProxyUpdateRequest,
)
from xfox.engine.events import emit_event

router = APIRouter(prefix="/api/proxies", tags=["proxies"])

ManagerUser = Annotated[XAccountRow, Depends(require(Permission.PROXIES_MANAGE))]


class ProxyCheckResponse(BaseModel):
    ok: bool
    latency_ms: int | None = None
    error: str | None = None


@router.get("", response_model=list[ProxyPublic])
async def list_proxies(
    db: DbDep, _user: Annotated[Any, Depends(require(Permission.PROXIES_READ))]
) -> list[ProxyPublic]:
    rows = await proxies_repo.list_proxies(db)
    return [ProxyPublic.model_validate(row) for row in rows]


@router.post("", response_model=ProxyPublic, status_code=status.HTTP_201_CREATED)
async def create_proxy(payload: ProxyCreateRequest, db: DbDep, _user: ManagerUser) -> ProxyPublic:
    if await proxies_repo.get_by_url(db, payload.url) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "proxy_url_exists")
    row = await proxies_repo.create_proxy(db, url=payload.url, label=payload.label)
    await emit_event(
        db,
        type=EventType.PROXY_CREATED,
        level=EventLevel.SUCCESS,
        category=EventCategory.SYSTEM,
        message=f"Proxy added: {row.label or row.url}",
    )
    await db.flush()
    return ProxyPublic.model_validate(row)


@router.patch("/{proxy_id}", response_model=ProxyPublic)
async def update_proxy(
    proxy_id: int, payload: ProxyUpdateRequest, db: DbDep, _user: ManagerUser
) -> ProxyPublic:
    row = await proxies_repo.get_proxy(db, proxy_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proxy_not_found")
    await proxies_repo.update_proxy(
        db,
        row,
        label=payload.label if payload.label is not None else row.label,
        url=payload.url if payload.url is not None else row.url,
        status=payload.status if payload.status is not None else row.status,
    )
    await emit_event(
        db,
        type=EventType.PROXY_UPDATED,
        level=EventLevel.INFO,
        category=EventCategory.SYSTEM,
        message=f"Proxy '{row.label or row.url}' updated",
    )
    await db.flush()
    return ProxyPublic.model_validate(row)


@router.delete("/{proxy_id}", response_model=MessageResponse)
async def delete_proxy(proxy_id: int, db: DbDep, _user: ManagerUser) -> MessageResponse:
    row = await proxies_repo.get_proxy(db, proxy_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proxy_not_found")
    await proxies_repo.delete_proxy(db, row)
    await emit_event(
        db,
        type=EventType.PROXY_DELETED,
        level=EventLevel.WARNING,
        category=EventCategory.SYSTEM,
        message=f"Proxy '{row.label or row.url}' deleted",
    )
    await db.flush()
    return MessageResponse(message="proxy_deleted")


@router.post("/{proxy_id}/check", response_model=ProxyCheckResponse)
async def check_proxy(proxy_id: int, db: DbDep, _user: ManagerUser) -> ProxyCheckResponse:
    """Test the proxy by reaching x.com through it."""
    row = await proxies_repo.get_proxy(db, proxy_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proxy_not_found")

    started = time.monotonic()
    ok = False
    error: str | None = None
    try:
        async with httpx.AsyncClient(proxy=row.url, timeout=12.0, follow_redirects=True) as client:
            response = await client.get("https://x.com/robots.txt")
            ok = response.status_code < 500
            if not ok:
                error = f"status_{response.status_code}"
    except Exception as exc:  # noqa: BLE001 - report any transport error
        error = type(exc).__name__

    latency_ms = int((time.monotonic() - started) * 1000) if ok else None
    await proxies_repo.record_check(db, proxy_id, ok=ok, latency_ms=latency_ms)
    await emit_event(
        db,
        type=EventType.PROXY_CHECKED,
        level=EventLevel.SUCCESS if ok else EventLevel.WARNING,
        category=EventCategory.SYSTEM,
        message=f"Proxy '{row.label or row.url}' check: {'OK' if ok else 'FAILED'}"
        + (f" ({latency_ms}ms)" if latency_ms else ""),
        params={"ok": ok, "latency_ms": latency_ms, "error": error},
    )
    await db.flush()
    return ProxyCheckResponse(ok=ok, latency_ms=latency_ms, error=error)
