"""Application-settings repository (JSON document under a single key)."""

from sqlalchemy.ext.asyncio import AsyncSession

from xfox.db.models import SettingsRow
from xfox.domain.policies import AppSettings

_SETTINGS_KEY = "app"


async def load_app_settings(session: AsyncSession) -> AppSettings:
    """Load persisted settings, falling back to safe defaults per field."""
    row = await session.get(SettingsRow, _SETTINGS_KEY)
    if row is None:
        return AppSettings()
    return AppSettings.model_validate(row.value)


async def save_app_settings(session: AsyncSession, value: AppSettings) -> None:
    row = await session.get(SettingsRow, _SETTINGS_KEY)
    if row is None:
        row = SettingsRow(key=_SETTINGS_KEY, value=value.model_dump(mode="json"))
        session.add(row)
    else:
        row.value = value.model_dump(mode="json")
    await session.flush()
