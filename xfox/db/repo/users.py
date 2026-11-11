"""Console-user repository."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import UserRow


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(UserRow))
    return int(result.scalar_one())


async def get_by_username(session: AsyncSession, username: str) -> UserRow | None:
    result = await session.execute(
        select(UserRow).where(UserRow.username == username.lower())
    )
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, user_id: int) -> UserRow | None:
    return await session.get(UserRow, user_id)


async def list_users(session: AsyncSession) -> list[UserRow]:
    result = await session.execute(select(UserRow).order_by(UserRow.id))
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password_hash: str,
    role: str,
    display_name: str | None = None,
) -> UserRow:
    user = UserRow(
        username=username.lower(),
        display_name=display_name,
        password_hash=password_hash,
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def touch_last_login(session: AsyncSession, user_id: int) -> None:
    user = await session.get(UserRow, user_id)
    if user is not None:
        user.last_login_at = datetime.now(tz=UTC)
        await session.flush()


async def delete_user(session: AsyncSession, user: UserRow) -> None:
    await session.delete(user)
    await session.flush()
