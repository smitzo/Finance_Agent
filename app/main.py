"""
Application Entry Point: Creates the FastAPI app, initializes DB schema, and builds the in-memory graph.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.models.db_models import Base
from app.services.graph_service import get_graph_service

settings = get_settings()
logger = logging.getLogger(__name__)

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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        graph_service = get_graph_service()
        await graph_service.build(db)
        logger.info("Graph built successfully")
