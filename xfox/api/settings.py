"""Application settings endpoints (typed, validated, hot-reloaded)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from xfox.api.deps import DbDep, require
from xfox.db.models import XAccountRow
from xfox.db.repo import settings as settings_repo
from xfox.domain.enums import EventCategory, EventLevel, EventType, Permission
from xfox.domain.policies import AppSettings
from xfox.engine.events import emit_event
from xfox.engine.orchestrator import get_engine

router = APIRouter(prefix="/api/settings", tags=["settings"])

ReaderUser = Annotated[Any, Depends(require(Permission.SETTINGS_READ))]
ManagerUser = Annotated[XAccountRow, Depends(require(Permission.SETTINGS_MANAGE))]


@router.get("", response_model=AppSettings)
async def get_settings(db: DbDep, _user: ReaderUser) -> AppSettings:
    return await settings_repo.load_app_settings(db)


@router.put("", response_model=AppSettings)
async def update_settings(payload: AppSettings, db: DbDep, _user: ManagerUser) -> AppSettings:
    await settings_repo.save_app_settings(db, payload)
    await emit_event(
        db,
        type=EventType.SETTINGS_UPDATED,
        level=EventLevel.INFO,
        category=EventCategory.SYSTEM,
        message="Anti-ban and scheduling settings updated",
    )
    await db.flush()
    get_engine().app_settings = payload  # hot-reload into the engine
    get_engine().wake()
    return payload
