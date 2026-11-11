"""Application configuration.

A single, typed source of truth for every runtime knob. Values come from the
environment (``XFOX_`` prefix) so the same image can run in any environment
without code changes. See ``.env.example`` for documented defaults.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(
        env_prefix="XFOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    environment: Literal["production", "development"] = "production"

    # --- Storage ---
    data_dir: Path = Path("./data")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://xfox:xfox_password@localhost:5432/xfox"

    # --- Security ---
    secret_key: str = "CHANGE_ME_GENERATE_A_LONG_RANDOM_STRING"
    cookie_secure: bool = False
    session_days: int = Field(default=7, ge=1, le=90)

    # --- Logging ---
    log_level: str = "INFO"

    # --- X-CrawlFox engine ---
    crawlfox_bin: str = "x-crawlfox"
    camoufox_fetch_cmd: str = "camoufox fetch"

    @field_validator("data_dir")
    @classmethod
    def _absolute_data_dir(cls, value: Path) -> Path:
        """Resolve to an absolute path — the engine spawns subprocesses with a
        different working directory, so relative storage paths would break."""
        return value.expanduser().resolve()

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, value: str) -> str:
        """Accept plain ``postgresql://`` URLs and upgrade them to asyncpg."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def accounts_dir(self) -> Path:
        return self.data_dir / "accounts"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def run_logs_dir(self) -> Path:
        return self.data_dir / "run-logs"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import-safe, test-overridable)."""
    return Settings()


settings = get_settings()
