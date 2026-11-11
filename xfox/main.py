"""Application entrypoint — FastAPI factory, lifespan, SPA hosting, CLI runner.

Run in production:
    uvicorn xfox.main:app --host 0.0.0.0 --port 8000
Or via the console script:
    xfox
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from xfox import __version__
from xfox.api import (
    accounts,
    auth,
    data,
    events,
    exports,
    jobs,
    proxies,
    system,
    users,
)
from xfox.api import (
    settings as settings_routes,
)
from xfox.config import settings
from xfox.db.engine import dispose_engine
from xfox.engine.orchestrator import get_engine
from xfox.logs import setup_logging

_WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
_APP_DIST = Path(__file__).resolve().parent / "webui"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot the database, the harvesting engine, and orphan recovery."""
    setup_logging()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.accounts_dir.mkdir(parents=True, exist_ok=True)
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    settings.run_logs_dir.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    orphans = await engine.reap_orphans()
    if orphans:
        from loguru import logger

        logger.warning("Finalized {} orphaned runs from a previous session", orphans)
    await engine.start()

    from xfox.db.engine import get_session_factory
    from xfox.domain.enums import EventCategory, EventLevel, EventType
    from xfox.engine.events import emit_event

    async with get_session_factory()() as session:
        await emit_event(
            session,
            type=EventType.SERVER_STARTED,
            level=EventLevel.SUCCESS,
            category=EventCategory.SYSTEM,
            message=f"XFox Harvester v{__version__} started",
        )
        await session.commit()

    yield

    await engine.stop()
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the fully wired application."""
    app = FastAPI(
        title="XFox Harvester",
        version=__version__,
        description=(
            "Safe X (Twitter) post harvesting around X-CrawlFox — "
            "anti-ban governance included."
        ),
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(accounts.router)
    app.include_router(proxies.router)
    app.include_router(jobs.router)
    app.include_router(data.router)
    app.include_router(events.router)
    app.include_router(settings_routes.router)
    app.include_router(exports.router)
    app.include_router(system.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        from loguru import logger

        logger.exception("Unhandled error on {} {}", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal_error"})

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built React dashboard (with SPA history fallback)."""
    dist = _WEB_DIST if _WEB_DIST.exists() else _APP_DIST
    if not dist.exists():
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    index_html = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index_html))


app = create_app()


def run_server() -> None:
    """Console-script entrypoint (``xfox``)."""
    import uvicorn

    uvicorn.run(
        "xfox.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run_server()
