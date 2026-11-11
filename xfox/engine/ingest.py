"""Ingest mapper — CrawledItem JSONL documents → normalized :class:`IngestPost`s.

Field names follow the ``CrawledItem`` schema exported by X-CrawlFox 0.1.2
(``id, url, title, content, description, author{...}, media[...], stats{...},
publish_time, crawl_time, source, is_article, raw_data``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from xfox.domain.schemas import IngestPost


def _parse_time(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def map_item(raw: dict[str, Any]) -> IngestPost | None:
    """Map one raw item; returns ``None`` for unusable entries."""
    post_id = str(raw.get("id") or "").strip()
    if not post_id or post_id.startswith("unknown_"):
        return None  # X-CrawlFox assigns random ids to unparsed tweets

    author = raw.get("author") or {}
    username = str(author.get("username") or "").lstrip("@").strip().lower()
    if not username:
        return None

    stats = raw.get("stats") or {}
    media = [
        {
            "type": str(entry.get("type", "image")),
            "url": str(entry.get("url") or ""),
            "cover_url": entry.get("cover_url"),
        }
        for entry in (raw.get("media") or [])
        if isinstance(entry, dict) and entry.get("url")
    ]

    return IngestPost(
        post_id=post_id,
        author_username=username,
        author_nickname=author.get("nickname"),
        author_avatar=author.get("avatar_url"),
        author_profile=author.get("profile_url"),
        content=str(raw.get("content") or ""),
        description=raw.get("description"),
        title=raw.get("title"),
        url=raw.get("url"),
        source=str(raw.get("source") or ""),
        is_article=bool(raw.get("is_article", False)),
        stats={
            "likes": _as_int(stats.get("likes")),
            "comments": _as_int(stats.get("comments")),
            "shares": _as_int(stats.get("shares")),
            "views": _as_int(stats.get("views")),
        },
        media=media,
        publish_time=_parse_time(raw.get("publish_time")),
        crawl_time=_parse_time(raw.get("crawl_time")),
        raw=raw,
    )


def map_items(raw_items: list[dict[str, Any]]) -> tuple[list[IngestPost], int]:
    """Map a batch; returns ``(usable_posts, skipped_count)``."""
    posts: list[IngestPost] = []
    skipped = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        mapped = map_item(raw)
        if mapped is None:
            skipped += 1
        else:
            posts.append(mapped)
    return posts, skipped
