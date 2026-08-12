"""Celery tasks and API-facing enqueue helpers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine

from celery.signals import worker_process_shutdown

from app.agent.checkpoint import close_agent_runtime
from app.agent.execution import process_agent_for_bill, resume_agent_for_bill
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
_worker_loop: asyncio.AbstractEventLoop | None = None


def _run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Reuse one event loop per prefork child so async pools stay loop-bound."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop.run_until_complete(coroutine)


@celery_app.task(
    bind=True,
    name="freightflow.process_bill",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def process_bill_task(self, bill_id: str, bill: dict, correlation_id: str) -> dict:
    _run(process_agent_for_bill(bill_id, bill, correlation_id, self.request.id))
    return {"bill_id": bill_id, "status": "completed"}


@celery_app.task(
    bind=True,
    name="freightflow.resume_bill",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def resume_bill_task(
    self,
    bill_id: str,
    tenant_id: str,
    thread_id: str,
    reviewer_decision: str,
    reviewer_notes: str | None,
    correlation_id: str,
) -> dict:
    _run(
        resume_agent_for_bill(
            bill_id,
            tenant_id,
            thread_id,
            reviewer_decision,
            reviewer_notes,
            correlation_id,
            self.request.id,
        )
    )
    return {"bill_id": bill_id, "status": "completed"}


def enqueue_bill(bill_id: str, bill: dict, correlation_id: str) -> str:
    result = process_bill_task.delay(bill_id, bill, correlation_id)
    return result.id


def enqueue_review_resume(
    bill_id: str,
    tenant_id: str,
    thread_id: str,
    reviewer_decision: str,
    reviewer_notes: str | None,
    correlation_id: str,
) -> str:
    result = resume_bill_task.delay(
        bill_id,
        tenant_id,
        thread_id,
        reviewer_decision,
        reviewer_notes,
        correlation_id,
    )
    return result.id


@worker_process_shutdown.connect
def close_worker_runtime(**_kwargs) -> None:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        return
    try:
        _worker_loop.run_until_complete(close_agent_runtime())
    finally:
        _worker_loop.close()
        _worker_loop = None
