""" 
Database Session
================
Async SQLAlchemy engine + session factory.
FastAPI dependency `get_db` yields one session per request.
"""

from __future__ import annotations
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings

settings = get_settings()


def _normalize_async_database_url(url: str) -> str:
    """
    Ensure Postgres DSNs use asyncpg so SQLAlchemy async engine can start.
    Also removes `channel_binding`, which is commonly present in libpq URLs
    but not supported by asyncpg.
    """
    normalized = url.strip()

    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql+asyncpg://", 1)
    elif normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif normalized.startswith("postgresql+psycopg2://"):
        normalized = normalized.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    elif normalized.startswith("postgresql+psycopg://"):
        normalized = normalized.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    parts = urlsplit(normalized)
    query_pairs: list[tuple[str, str]] = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if k == "channel_binding":
            continue
        if k == "sslmode":
            query_pairs.append(("ssl", v))
            continue
        query_pairs.append((k, v))
    cleaned_query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, cleaned_query, parts.fragment))


database_url = _normalize_async_database_url(settings.database_url)

engine = create_async_engine(
    database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields a DB session, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
