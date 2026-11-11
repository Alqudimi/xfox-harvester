"""Proxy repository."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import ProxyRow


async def list_proxies(session: AsyncSession) -> list[ProxyRow]:
    result = await session.execute(select(ProxyRow).order_by(ProxyRow.id))
    return list(result.scalars().all())


async def get_proxy(session: AsyncSession, proxy_id: int) -> ProxyRow | None:
    return await session.get(ProxyRow, proxy_id)


async def get_by_url(session: AsyncSession, url: str) -> ProxyRow | None:
    result = await session.execute(select(ProxyRow).where(ProxyRow.url == url))
    return result.scalar_one_or_none()


async def create_proxy(session: AsyncSession, *, url: str, label: str | None = None) -> ProxyRow:
    row = ProxyRow(url=url, label=label, status="active")
    session.add(row)
    await session.flush()
    return row


async def update_proxy(session: AsyncSession, proxy: ProxyRow, **fields: object) -> ProxyRow:
    for key, value in fields.items():
        setattr(proxy, key, value)
    await session.flush()
    return proxy


async def delete_proxy(session: AsyncSession, proxy: ProxyRow) -> None:
    await session.delete(proxy)
    await session.flush()


async def record_check(
    session: AsyncSession, proxy_id: int, *, ok: bool, latency_ms: int | None
) -> None:
    proxy = await session.get(ProxyRow, proxy_id)
    if proxy is None:
        return
    proxy.last_check_at = datetime.now(tz=UTC)
    proxy.latency_ms = latency_ms if ok else None
    if not ok:
        proxy.status = "disabled"
    elif proxy.status == "disabled":
        proxy.status = "active"
    await session.flush()
