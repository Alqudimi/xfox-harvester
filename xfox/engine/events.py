"""In-process event bus feeding the SSE stream.

Publishers (API handlers, engine components) first persist an event row, then
push it here. Each subscriber owns an ``asyncio.Queue``; slow consumers never
block the system — events are dropped for them when their queue is full (SSE
clients also have the REST history endpoint as a fallback).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from xfox.domain.enums import EventCategory, EventLevel, EventType

_MAX_QUEUE = 200
_RECENT_BUFFER = 500


@dataclass
class _Subscriber:
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_MAX_QUEUE)
    )


class EventBus:
    """Fan-out broadcast of engine events to live listeners."""

    def __init__(self) -> None:
        self._subscribers: list[_Subscriber] = []
        self._recent: list[dict[str, Any]] = []

    def subscribe(self) -> _Subscriber:
        subscriber = _Subscriber()
        self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    def publish(self, event: dict[str, Any]) -> None:
        """Broadcast *event* to every live subscriber (non-blocking)."""
        self._recent.append(event)
        if len(self._recent) > _RECENT_BUFFER:
            self._recent = self._recent[-_RECENT_BUFFER:]
        for subscriber in list(self._subscribers):
            try:
                subscriber.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop for this slow consumer only.
                continue

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._recent[-limit:]

    async def stream(self, subscriber: _Subscriber) -> AsyncIterator[dict[str, Any]]:
        """Yield events as they arrive (used by the SSE endpoint)."""
        while True:
            event = await subscriber.queue.get()
            yield event


def build_event_payload(
    *,
    event_id: int | None,
    type: EventType,
    level: EventLevel,
    category: EventCategory,
    message: str,
    params: dict[str, Any] | None = None,
    account_id: int | None = None,
    job_id: int | None = None,
    run_id: int | None = None,
    ts: datetime | None = None,
) -> dict[str, Any]:
    """Shape used on the wire (REST + SSE share it)."""
    return {
        "id": event_id,
        "ts": (ts or datetime.now(tz=UTC)).isoformat(),
        "type": type.value,
        "level": level.value,
        "category": category.value,
        "message": message,
        "params": params,
        "account_id": account_id,
        "job_id": job_id,
        "run_id": run_id,
    }


# Single process-wide bus instance.
bus = EventBus()


async def emit_event(
    session,
    *,
    type: EventType,
    level: EventLevel,
    category: EventCategory,
    message: str,
    params: dict[str, Any] | None = None,
    account_id: int | None = None,
    job_id: int | None = None,
    run_id: int | None = None,
) -> dict[str, Any]:
    """Persist an event row and broadcast it on the bus (API + engine share this)."""
    from xfox.db.repo import events as events_repo

    row = await events_repo.add_event(
        session,
        type=type.value,
        level=level.value,
        category=category.value,
        message=message,
        params=params,
        account_id=account_id,
        job_id=job_id,
        run_id=run_id,
    )
    payload = build_event_payload(
        event_id=row.id,
        type=type,
        level=level,
        category=category,
        message=message,
        params=params,
        account_id=account_id,
        job_id=job_id,
        run_id=run_id,
        ts=row.ts,
    )
    bus.publish(payload)
    return payload
