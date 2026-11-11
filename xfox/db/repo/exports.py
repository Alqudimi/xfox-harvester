"""Export-task repository."""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import ExportRow


async def create_export(
    session: AsyncSession,
    *,
    entity: str,
    format: str,
    filters: dict,
    created_by: int | None,
) -> ExportRow:
    row = ExportRow(
        entity=entity,
        format=format,
        filters=filters,
        status="pending",
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def update_export(session: AsyncSession, export_id: int, **fields: object) -> None:
    row = await session.get(ExportRow, export_id)
    if row is not None:
        for key, value in fields.items():
            setattr(row, key, value)
        await session.flush()


async def get_export(session: AsyncSession, export_id: int) -> ExportRow | None:
    return await session.get(ExportRow, export_id)


async def list_exports(
    session: AsyncSession, *, page: int = 1, page_size: int = 20
) -> tuple[list[ExportRow], int]:
    from sqlalchemy import func

    total = int(
        (await session.execute(select(func.count()).select_from(ExportRow))).scalar_one()
    )
    rows = await session.execute(
        select(ExportRow).order_by(ExportRow.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows.scalars().all()), total
