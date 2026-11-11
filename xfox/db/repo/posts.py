"""Post repository — idempotent ingestion and faceted querying.

Search uses ``ILIKE`` backed by ``pg_trgm`` GIN indexes (created in the initial
migration), which handles Arabic and English text uniformly without needing a
language-specific tokenizer.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Integer, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import AuthorRow, PostRow
from xfox.db.repo.authors import upsert_author
from xfox.domain.schemas import IngestPost, PostFilter


async def ingest_posts(
    session: AsyncSession,
    items: list[IngestPost],
    *,
    run_id: int | None = None,
    keep_raw: bool = True,
) -> tuple[int, int]:
    """Upsert a batch of posts. Returns ``(inserted_new, total_seen)``."""
    author_ids: dict[str, int] = {}
    inserted = 0
    for item in items:
        if item.author_username not in author_ids:
            author_ids[item.author_username] = await upsert_author(
                session,
                username=item.author_username,
                nickname=item.author_nickname,
                avatar_url=item.author_avatar,
                profile_url=item.author_profile,
            )
        stmt = (
            pg_insert(PostRow)
            .values(
                post_id=item.post_id,
                author_id=author_ids[item.author_username],
                content=item.content,
                description=item.description,
                title=item.title,
                url=item.url,
                source=item.source,
                is_article=item.is_article,
                stats=item.stats,
                media=item.media,
                publish_time=item.publish_time,
                crawl_time=item.crawl_time or datetime.now(tz=UTC),
                first_seen_run_id=run_id,
                raw=item.raw if keep_raw else None,
            )
            .on_conflict_do_nothing(index_elements=[PostRow.post_id])
        )
        result = await session.execute(stmt)
        inserted += result.rowcount or 0
    return inserted, len(items)


def _likes_expr():
    return PostRow.stats["likes"].astext.cast(Integer)


def _views_expr():
    return PostRow.stats["views"].astext.cast(Integer)


async def query_posts(
    session: AsyncSession, filters: PostFilter
) -> tuple[list[tuple[PostRow, AuthorRow]], int]:
    """Filtered, sorted, paginated posts joined with their authors."""
    stmt = select(PostRow, AuthorRow).join(AuthorRow, PostRow.author_id == AuthorRow.id)

    conditions = []
    if filters.q:
        pattern = f"%{filters.q}%"
        conditions.append(
            PostRow.content.ilike(pattern)
            | PostRow.description.ilike(pattern)
            | AuthorRow.username.ilike(pattern)
        )
    if filters.author:
        conditions.append(AuthorRow.username == filters.author.lstrip("@").lower())
    if filters.sources:
        conditions.append(PostRow.source.in_(filters.sources))
    if filters.date_from:
        conditions.append(PostRow.publish_time >= filters.date_from)
    if filters.date_to:
        conditions.append(PostRow.publish_time <= filters.date_to)
    if filters.min_likes is not None:
        conditions.append(_likes_expr() >= filters.min_likes)
    if filters.min_views is not None:
        conditions.append(_views_expr() >= filters.min_views)
    if filters.has_media is True:
        conditions.append(func.jsonb_array_length(PostRow.media) > 0)
    elif filters.has_media is False:
        conditions.append(func.jsonb_array_length(PostRow.media) == 0)

    if conditions:
        stmt = stmt.where(*conditions)

    total = int(
        (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    )

    descending = filters.order == "desc"
    sort_map = {
        "publish_time": PostRow.publish_time.desc() if descending else PostRow.publish_time.asc(),
        "crawl_time": PostRow.crawl_time.desc() if descending else PostRow.crawl_time.asc(),
        "likes": _likes_expr().desc() if descending else _likes_expr().asc(),
        "views": _views_expr().desc() if descending else _views_expr().asc(),
    }
    stmt = stmt.order_by(sort_map[filters.sort].nullslast(), PostRow.post_id)

    rows = await session.execute(
        stmt.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
    )
    return [tuple(row) for row in rows.all()], total


async def count_posts(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(PostRow))
    return int(result.scalar_one())


async def count_posts_since(session: AsyncSession, since: datetime) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(PostRow)
        .where(PostRow.first_seen_run_id.is_not(None))
        .where(PostRow.crawl_time >= since)
    )
    return int(result.scalar_one())


async def daily_counts(session: AsyncSession, days: int = 14) -> list[dict]:
    """Harvested-post counts per day for dashboard charts."""
    start = (datetime.now(tz=UTC) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    day = func.date_trunc("day", PostRow.crawl_time).label("day")
    stmt = (
        select(day, func.count().label("count"))
        .where(PostRow.crawl_time >= start)
        .group_by(day)
        .order_by(day)
    )
    result = await session.execute(stmt)
    by_date = {row.day.date().isoformat(): int(row.count) for row in result.all()}
    return [
        {
            "date": (day := (start + timedelta(days=offset)).date()).isoformat(),
            "count": by_date.get(day.isoformat(), 0),
        }
        for offset in range(days)
    ]


async def iter_posts_for_export(
    session: AsyncSession, filters: PostFilter, chunk_size: int = 500
):
    """Yield (post, author) tuples matching the filters — used by exporters."""
    filters.page = 1
    filters.page_size = chunk_size
    while True:
        rows, _total = await query_posts(session, filters)
        if not rows:
            break
        yield rows
        filters.page += 1
