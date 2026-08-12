"""Structured JSON logging and correlation context shared by API and workers."""

from __future__ import annotations

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
from fastapi import Request
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    merge_contextvars,
)

from app.config import get_settings

settings = get_settings()


def configure_logging() -> Path:
    """Configure stdlib and structlog events through one JSON renderer."""
    logs_dir = Path(settings.log_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = logs_dir / settings.log_file_name

    shared_processors = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    handlers.append(
        RotatingFileHandler(
            filename=log_file_path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
    )
    for handler in handlers:
        handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    for handler in handlers:
        root_logger.addHandler(handler)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return log_file_path


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def current_correlation_id() -> str:
    return str(get_contextvars().get("correlation_id") or new_correlation_id())


async def correlation_middleware(request: Request, call_next):
    """Bind request metadata and return the correlation ID to API clients."""
    clear_contextvars()
    correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
    bind_contextvars(
        correlation_id=correlation_id,
        http_method=request.method,
        http_path=request.url.path,
    )
    request.state.correlation_id = correlation_id
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        clear_contextvars()
