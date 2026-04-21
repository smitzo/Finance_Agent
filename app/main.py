"""
Application Entry Point: Creates the FastAPI app, initializes DB schema, and builds the in-memory graph.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router as api_router
from app.config import get_settings
from app.db.session import AsyncSessionLocal, database_url, engine
from app.models.db_models import Base
from app.services.graph_service import get_graph_service

settings = get_settings()


def _configure_logging() -> Path:
    logs_dir = Path(settings.log_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = logs_dir / settings.log_file_name

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(
                filename=log_file_path,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            ),
        ],
        force=True,
    )
    return log_file_path


_log_file_path = _configure_logging()
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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Startup: database schema ensured")

    async with AsyncSessionLocal() as db:
        graph_service = get_graph_service()
        await graph_service.build(db)
        logger.info("Startup: graph built successfully")
