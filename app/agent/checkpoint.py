"""Process-local durable LangGraph runtime backed by PostgreSQL checkpoints."""

from __future__ import annotations

import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.agent import build_agent
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_agent = None


def checkpoint_database_url(url: str) -> str:
    """Convert SQLAlchemy/asyncpg DSNs to the psycopg DSN used by the saver."""
    normalized = url.strip()
    for scheme in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgres://",
    ):
        if normalized.startswith(scheme):
            normalized = normalized.replace(scheme, "postgresql://", 1)
            break

    parts = urlsplit(normalized)
    query_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "channel_binding":
            continue
        if key == "ssl":
            query_pairs.append(("sslmode", value))
            continue
        query_pairs.append((key, value))
    query = urlencode(query_pairs, doseq=True)
    if parts.scheme and not parts.netloc and normalized.startswith(f"{parts.scheme}:///"):
        # urlunsplit collapses an empty authority to ``scheme:/path``; psycopg
        # requires the original triple-slash URI for Unix-socket connections.
        suffix = f"?{query}" if query else ""
        return f"{parts.scheme}://{parts.path}{suffix}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


async def initialize_agent_runtime():
    """Open the checkpoint pool once per Celery worker process."""
    global _pool, _checkpointer, _agent
    if _agent is not None:
        return _agent

    _pool = AsyncConnectionPool(
        conninfo=checkpoint_database_url(settings.database_url),
        min_size=1,
        max_size=max(1, settings.checkpoint_pool_size),
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await _pool.open(wait=True)
    _checkpointer = AsyncPostgresSaver(_pool)
    _agent = build_agent(_checkpointer)
    logger.info("Durable LangGraph checkpoint runtime initialized")
    return _agent


async def setup_checkpoint_schema() -> None:
    """Create or upgrade LangGraph-owned tables before workers start."""
    async with AsyncPostgresSaver.from_conn_string(
        checkpoint_database_url(settings.database_url)
    ) as checkpointer:
        await checkpointer.setup()
    logger.info("Durable LangGraph checkpoint schema is ready")


async def get_agent():
    return await initialize_agent_runtime()


async def close_agent_runtime() -> None:
    global _pool, _checkpointer, _agent
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None
    _agent = None
