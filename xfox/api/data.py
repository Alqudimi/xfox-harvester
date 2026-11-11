"""Harvested-data endpoints — posts explorer and author directory."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from xfox.api.deps import DbDep, require
from xfox.db.repo import authors as authors_repo
from xfox.db.repo import posts as posts_repo
from xfox.domain.enums import Permission
from xfox.domain.schemas import (
    AuthorBrief,
    AuthorPage,
    AuthorPublic,
    MediaItem,
    PostFilter,
    PostPage,
    PostPublic,
    PostStats,
)

router = APIRouter(prefix="/api/data", tags=["data"])

ReaderUser = Annotated[Any, Depends(require(Permission.DATA_READ))]


def _post_public(post, author) -> PostPublic:
    stats = post.stats or {}
    return PostPublic(
        id=post.post_id,
        author=AuthorBrief(
            username=author.username,
            nickname=author.nickname,
            avatar_url=author.avatar_url,
        ),
        content=post.content,
        description=post.description,
        url=post.url,
        source=post.source,
        is_article=bool(post.is_article),
        stats=PostStats(
            likes=int(stats.get("likes", 0) or 0),
            comments=int(stats.get("comments", 0) or 0),
            shares=int(stats.get("shares", 0) or 0),
            views=int(stats.get("views", 0) or 0),
        ),
        media=[MediaItem(**m) for m in (post.media or []) if isinstance(m, dict) and m.get("url")],
        publish_time=post.publish_time,
        crawl_time=post.crawl_time,
    )


@router.get("/posts", response_model=PostPage)
async def list_posts(
    db: DbDep,
    _user: ReaderUser,
    filters: Annotated[PostFilter, Query()],
) -> PostPage:
    rows, total = await posts_repo.query_posts(db, filters)
    return PostPage(
        items=[_post_public(post, author) for post, author in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/authors", response_model=AuthorPage)
async def list_authors(
    db: DbDep,
    _user: ReaderUser,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=200),
) -> AuthorPage:
    rows, total = await authors_repo.list_authors(db, q=q, page=page, page_size=page_size)
    items = [
        AuthorPublic(
            username=row["username"],
            nickname=row["nickname"],
            avatar_url=row["avatar_url"],
            profile_url=row["profile_url"],
            posts_count=int(row["posts_count"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )
        for row in rows
    ]
    return AuthorPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/sources", response_model=list[str])
async def list_sources(db: DbDep, _user: ReaderUser) -> list[str]:
    from sqlalchemy import select

    from xfox.db.models import PostRow

    result = await db.execute(select(PostRow.source).distinct().order_by(PostRow.source))
    return [row[0] for row in result.all() if row[0]]
