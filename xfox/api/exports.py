"""Export endpoints — posts/authors to CSV, JSON, or XLSX (background jobs)."""

from __future__ import annotations

import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from xfox.api.deps import CurrentUser, DbDep, require
from xfox.config import settings as app_config
from xfox.db.engine import get_session_factory
from xfox.db.models import XAccountRow
from xfox.db.repo import authors as authors_repo
from xfox.db.repo import exports as exports_repo
from xfox.db.repo import posts as posts_repo
from xfox.domain.enums import EventCategory, EventLevel, EventType, Permission
from xfox.domain.schemas import ExportCreateRequest, ExportPublic, PostFilter
from xfox.engine.events import emit_event

router = APIRouter(prefix="/api/exports", tags=["exports"])

ManagerUser = Annotated[XAccountRow, Depends(require(Permission.DATA_EXPORT))]
ReaderUser = Annotated[Any, Depends(require(Permission.DATA_READ))]


@router.post("", response_model=ExportPublic, status_code=status.HTTP_201_CREATED)
async def create_export(
    payload: ExportCreateRequest, db: DbDep, user: CurrentUser
) -> ExportPublic:
    from xfox.domain.enums import Role
    from xfox.domain.permissions import role_has

    if not role_has(Role(user.role), Permission.DATA_EXPORT):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission_denied")

    row = await exports_repo.create_export(
        db,
        entity=payload.entity.value,
        format=payload.format.value,
        filters=payload.filters.model_dump(mode="json"),
        created_by=user.id,
    )
    await emit_event(
        db,
        type=EventType.EXPORT_CREATED,
        level=EventLevel.INFO,
        category=EventCategory.EXPORT,
        message=f"Export #{row.id} queued ({payload.entity.value} → {payload.format.value})",
        params={"entity": payload.entity.value, "format": payload.format.value},
    )
    await db.flush()

    asyncio.create_task(_generate_export(row.id, payload))
    return ExportPublic.model_validate(row)


@router.get("", response_model=list[ExportPublic])
async def list_exports(
    db: DbDep, _user: ReaderUser, page: int = 1, page_size: int = 20
) -> list[ExportPublic]:
    rows, _total = await exports_repo.list_exports(db, page=page, page_size=page_size)
    return [ExportPublic.model_validate(row) for row in rows]


@router.get("/{export_id}", response_model=ExportPublic)
async def get_export(export_id: int, db: DbDep, _user: ReaderUser) -> ExportPublic:
    row = await exports_repo.get_export(db, export_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "export_not_found")
    return ExportPublic.model_validate(row)


@router.get("/{export_id}/download")
async def download_export(export_id: int, db: DbDep, _user: ReaderUser) -> FileResponse:
    row = await exports_repo.get_export(db, export_id)
    if row is None or row.status != "done" or not row.file_name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "export_not_ready")

    path = app_config.exports_dir / row.file_name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "export_file_missing")

    media_type = {
        "csv": "text/csv",
        "json": "application/json",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(row.format, "application/octet-stream")
    return FileResponse(path, filename=row.file_name, media_type=media_type)


# ---------------------------------------------------------------------------
# Generation (background task)
# ---------------------------------------------------------------------------


async def _generate_export(export_id: int, request: ExportCreateRequest) -> None:
    """Build the export file and update its row. Runs detached from the request."""
    session_factory = get_session_factory()
    try:
        async with session_factory() as session:
            await exports_repo.update_export(session, export_id, status="running")
            await session.commit()

        app_config.exports_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"export-{export_id}-{datetime.now(tz=UTC):%Y%m%d%H%M%S}.{request.format.value}"
        path = app_config.exports_dir / file_name

        rows_written = 0
        filters = (
            request.filters
            if isinstance(request.filters, PostFilter)
            else PostFilter(**request.filters)
        )
        if request.entity.value == "posts":
            rows_written = await _export_posts(path, filters, request.format.value)
        else:
            rows_written = await _export_authors(path, request.format.value)

        async with session_factory() as session:
            await exports_repo.update_export(
                session,
                export_id,
                status="done",
                rows=rows_written,
                file_name=file_name,
                size_bytes=path.stat().st_size,
                finished_at=datetime.now(tz=UTC),
            )
            await session.commit()
            await _emit_export_event(session, export_id, True, rows_written)
    except Exception as exc:  # noqa: BLE001 - record any failure on the row
        async with session_factory() as session:
            await exports_repo.update_export(
                session, export_id, status="failed", error=str(exc)[:500]
            )
            await session.commit()
            await _emit_export_event(session, export_id, False, 0, str(exc)[:200])


async def _emit_export_event(
    session, export_id: int, ok: bool, rows: int, error: str | None = None
) -> None:
    await emit_event(
        session,
        type=EventType.EXPORT_FINISHED if ok else EventType.EXPORT_FAILED,
        level=EventLevel.SUCCESS if ok else EventLevel.ERROR,
        category=EventCategory.EXPORT,
        message=f"Export #{export_id} {'finished' if ok else 'failed'}"
        + (f" ({rows} rows)" if ok else f": {error}"),
        params={"rows": rows} if ok else {"error": error},
    )
    await session.commit()


async def _export_posts(path: Path, filters: PostFilter, fmt: str) -> int:
    filters.page = 1
    filters.page_size = 500

    async with get_session_factory()() as session:
        chunks: list[list[dict]] = []
        while True:
            rows, _total = await posts_repo.query_posts(session, filters)
            if not rows:
                break
            chunks.append([_post_dict(post, author) for post, author in rows])
            filters.page += 1

    flat = [row for chunk in chunks for row in chunk]
    await _write_file(path, fmt, flat)
    return len(flat)


async def _export_authors(path: Path, fmt: str) -> int:
    page, page_size = 1, 500
    rows_out: list[dict] = []
    async with get_session_factory()() as session:
        while True:
            rows, _total = await authors_repo.list_authors(
                session, page=page, page_size=page_size
            )
            if not rows:
                break
            rows_out.extend(
                [
                    {
                        "username": row["username"],
                        "nickname": row["nickname"],
                        "profile_url": row["profile_url"],
                        "posts_count": int(row["posts_count"]),
                        "first_seen": row["first_seen"].isoformat() if row["first_seen"] else None,
                        "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
                    }
                    for row in rows
                ]
            )
            page += 1
    await _write_file(path, fmt, rows_out)
    return len(rows_out)


def _post_dict(post, author) -> dict:
    stats = post.stats or {}
    return {
        "post_id": post.post_id,
        "author": author.username,
        "author_name": author.nickname,
        "content": post.content,
        "description": post.description,
        "url": post.url,
        "source": post.source,
        "likes": stats.get("likes", 0),
        "comments": stats.get("comments", 0),
        "shares": stats.get("shares", 0),
        "views": stats.get("views", 0),
        "media_count": len(post.media or []),
        "publish_time": post.publish_time.isoformat() if post.publish_time else None,
        "crawl_time": post.crawl_time.isoformat() if post.crawl_time else None,
    }


async def _write_file(path: Path, fmt: str, rows: list[dict]) -> None:
    """Write rows to disk without blocking the event loop for large sets."""
    if not rows:
        rows = []

    def _sync_write() -> None:
        if fmt == "json":
            path.write_text(
                json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
        elif fmt == "csv":
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
                writer.writeheader()
                writer.writerows(rows)
        elif fmt == "xlsx":
            from openpyxl import Workbook

            workbook = Workbook(write_only=True)
            sheet = workbook.create_sheet("data")
            if rows:
                headers = list(rows[0].keys())
                sheet.append(headers)
                for row in rows:
                    sheet.append([row.get(header) for header in headers])
            workbook.save(path)
        else:
            raise ValueError(f"unsupported format: {fmt}")

    await asyncio.to_thread(_sync_write)
