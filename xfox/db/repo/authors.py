"""Author repository."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import AuthorRow, PostRow


async def upsert_author(
    session: AsyncSession,
    *,
    username: str,
    nickname: str | None = None,
    avatar_url: str | None = None,
    profile_url: str | None = None,
) -> int:
    """Insert or refresh an author; returns the author id."""
    now = datetime.now(tz=UTC)
    stmt = (
        pg_insert(AuthorRow)
        .values(
            username=username,
            nickname=nickname,
            avatar_url=avatar_url,
            profile_url=profile_url,
            first_seen=now,
            last_seen=now,
        )
        .on_conflict_do_update(
            index_elements=[AuthorRow.username],
            set_={
                "nickname": nickname or AuthorRow.nickname,
                "avatar_url": avatar_url or AuthorRow.avatar_url,
                "profile_url": profile_url or AuthorRow.profile_url,
                "last_seen": now,
            },
        )
        .returning(AuthorRow.id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def count_authors(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(AuthorRow))
    return int(result.scalar_one())


async def top_authors(session: AsyncSession, limit: int = 8) -> list[dict]:
    """Authors with the most harvested posts."""
    stmt = (
        select(
            AuthorRow.username,
            AuthorRow.nickname,
            AuthorRow.avatar_url,
            AuthorRow.profile_url,
            AuthorRow.first_seen,
            AuthorRow.last_seen,
            func.count(PostRow.post_id).label("posts_count"),
        )
        .join(PostRow, PostRow.author_id == AuthorRow.id)
        .group_by(AuthorRow.id)
        .order_by(func.count(PostRow.post_id).desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [dict(row._mapping) for row in result.all()]


async def list_authors(
    session: AsyncSession, *, q: str | None = None, page: int = 1, page_size: int = 25
) -> tuple[list[dict], int]:
    """Authors with their post counts, filtered by an optional substring."""
    base = (
        select(
            AuthorRow.username,
            AuthorRow.nickname,
            AuthorRow.avatar_url,
            AuthorRow.profile_url,
            AuthorRow.first_seen,
            AuthorRow.last_seen,
            func.count(PostRow.post_id).label("posts_count"),
        )
        .outerjoin(PostRow, PostRow.author_id == AuthorRow.id)
        .group_by(AuthorRow.id)
    )
    if q:
        pattern = f"%{q}%"
        base = base.where(
            AuthorRow.username.ilike(pattern) | AuthorRow.nickname.ilike(pattern)
        )

    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = await session.execute(
        base.order_by(func.count(PostRow.post_id).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [dict(row._mapping) for row in rows.all()], total
