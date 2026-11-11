"""Event endpoints — history listing and the live SSE stream."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse

from xfox.api.deps import DbDep, get_current_user, require
from xfox.db.repo import events as events_repo
from xfox.domain.enums import Permission
from xfox.domain.schemas import EventPage, EventPublic
from xfox.engine.events import bus

router = APIRouter(prefix="/api/events", tags=["events"])

ReaderUser = Annotated[Any, Depends(require(Permission.EVENTS_READ))]


@router.get("", response_model=EventPage)
async def list_events(
    db: DbDep,
    _user: ReaderUser,
    level: str | None = None,
    category: str | None = None,
    q: str | None = None,
    job_id: int | None = None,
    account_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=5, le=200),
) -> EventPage:
    rows, total = await events_repo.list_events(
        db,
        level=level,
        category=category,
        q=q,
        account_id=account_id,
        job_id=job_id,
        page=page,
        page_size=page_size,
    )
    return EventPage(
        items=[EventPublic.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stream")
async def stream_events(
    _user: Annotated[Any, Depends(get_current_user)],
    category: str | None = None,
    level: str | None = None,
) -> EventSourceResponse:
    """Server-Sent Events feed of live engine happenings (cookie-authenticated)."""

    async def generator():
        subscriber = bus.subscribe()
        try:
            # Replay nothing — clients bootstrap from the REST history endpoint.
            while True:
                event = await subscriber.queue.get()
                if category and event.get("category") != category:
                    continue
                if level and event.get("level") != level:
                    continue
                yield {
                    "event": "message",
                    "data": json.dumps(event, default=str, ensure_ascii=False),
                }
        finally:
            bus.unsubscribe(subscriber)

    return EventSourceResponse(generator())
