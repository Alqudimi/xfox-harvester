"""Logging setup built on loguru.

Console output stays human-readable, while a rotating file under ``data/logs``
keeps the full history for troubleshooting. All engine events additionally flow
through the application event bus (see ``xfox.engine.events``) and are persisted
in the ``events`` table for the web console.
"""

import sys
from pathlib import Path

from loguru import logger

from xfox.config import settings

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging() -> None:
    """Configure loguru sinks. Safe to call multiple times."""
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.upper(), format=_FORMAT)

    log_dir: Path = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "xfox_{time:YYYY-MM-DD}.log",
        level=settings.log_level.upper(),
        format=_FORMAT,
        rotation="00:00",
        retention="14 days",
        compression="gz",
        encoding="utf-8",
        enqueue=True,
    )
