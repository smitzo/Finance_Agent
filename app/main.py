"""
Application entry point. Database schema changes are applied only by Alembic.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.dashboard_routes import router as dashboard_router
from app.api.routes import router as api_router
from app.config import get_settings
from app.db.session import AsyncSessionLocal, database_url, engine
from app.observability import configure_logging, correlation_middleware
from app.services.graph_service import get_graph_service

settings = get_settings()


_log_file_path = configure_logging()
logger = logging.getLogger(__name__)


def _redact_db_url(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    userinfo, hostinfo = parts.netloc.rsplit("@", 1)
    if ":" not in userinfo:
        return url
    user, _ = userinfo.split(":", 1)
    safe_netloc = f"{user}:***@{hostinfo}"
    return urlunsplit((parts.scheme, safe_netloc, parts.path, parts.query, parts.fragment))

if sys.platform == "win32":
    # Reduces noisy SSL shutdown errors seen with Proactor loop on Python 3.10.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI(
    title=settings.app_name,
    description="Freight bill processing system with LangGraph agent and human-in-the-loop review",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(correlation_middleware)

dashboard_static_dir = Path(__file__).resolve().parent / "dashboard" / "static"
app.mount("/dashboard/static", StaticFiles(directory=dashboard_static_dir), name="dashboard-static")

app.include_router(dashboard_router)
app.include_router(api_router)


@app.on_event("startup")
async def startup() -> None:
    logger.info("Startup: initializing service '%s'", settings.app_name)
    logger.info("Startup: logging to file '%s'", _log_file_path)
    logger.info("Startup: target database=%s", _redact_db_url(database_url))

    # Explicit DB connectivity check for easier local/prod debugging.
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Startup: database connectivity check passed")

    async with AsyncSessionLocal() as db:
        graph_service = get_graph_service()
        await graph_service.build(db, settings.default_tenant_id)
        logger.info("Startup: graph built successfully for tenant=%s", settings.default_tenant_id)


@app.on_event("shutdown")
async def shutdown() -> None:
    graph_service = get_graph_service()
    close = getattr(graph_service.backend, "close", None)
    if close:
        await close()
        logger.info("Shutdown: graph backend closed")
    await engine.dispose()
