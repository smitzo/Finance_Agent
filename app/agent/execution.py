"""Agent execution service used exclusively by Celery workers."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from structlog.contextvars import bind_contextvars, clear_contextvars

from app.agent.checkpoint import get_agent
from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.db_models import AuditLog, FreightBillStatus
from app.services.freight_service import get_bill, persist_result
from app.services.graph_service import get_graph_service

logger = logging.getLogger(__name__)
settings = get_settings()


def _initial_state(bill_id: str, tenant_id: str, bill: dict) -> dict:
    return {
        "bill": bill,
        "bill_id": bill_id,
        "tenant_id": tenant_id,
        "carrier": None,
        "carrier_id": bill.get("carrier_id"),
        "all_candidate_contracts": [],
        "chosen_contract": None,
        "shipment": None,
        "bols": [],
        "prior_billed_weight": 0.0,
        "existing_bill_ids": [],
        "graph_anomalies": [],
        "findings": [],
        "ambiguity_note": None,
        "confidence": 0.0,
        "decision": None,
        "explanation": None,
        "reviewer_decision": None,
        "reviewer_notes": None,
        "audit": [],
    }


async def process_agent_for_bill(
    bill_id: str,
    bill: dict,
    correlation_id: str,
    task_id: str | None = None,
) -> None:
    """Run a new workflow and persist final or interrupted state."""
    clear_contextvars()
    tenant_id = bill.get("tenant_id", settings.default_tenant_id)
    bind_contextvars(
        correlation_id=correlation_id,
        freight_bill_id=bill_id,
        tenant_id=tenant_id,
        celery_task_id=task_id,
    )
    # A bill can be deliberately reloaded in the demo environment. Each new
    # execution gets a fresh durable thread while review resumes use the exact
    # thread persisted on the bill.
    thread_id = f"thread-{tenant_id}-{bill_id}-{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": thread_id}}
    logger.info("Agent run started")

    try:
        graph_service = get_graph_service()
        async with AsyncSessionLocal() as db:
            await graph_service.ensure_built(db, tenant_id)
        await graph_service.add_freight_bill(tenant_id, bill_id, {**bill, "id": bill_id})

        async with AsyncSessionLocal() as db:
            freight_bill = await get_bill(db, bill_id, tenant_id)
            if freight_bill:
                freight_bill.status = FreightBillStatus.processing
                freight_bill.thread_id = thread_id
                freight_bill.correlation_id = correlation_id
                freight_bill.celery_task_id = task_id
                freight_bill.processing_started_at = datetime.utcnow()
                await db.commit()

        agent = await get_agent()
        try:
            async for _ in agent.astream(_initial_state(bill_id, tenant_id, bill), config=config):
                pass
            state_snapshot = await agent.aget_state(config)
            interrupted = bool(getattr(state_snapshot, "next", None))
            async with AsyncSessionLocal() as db:
                await persist_result(
                    db,
                    bill_id,
                    state_snapshot.values,
                    interrupted=interrupted,
                    tenant_id=tenant_id,
                )
            logger.info("Agent run completed", extra={"interrupted": interrupted})
        except Exception as exc:
            exc_name = type(exc).__name__
            if "GraphInterrupt" in exc_name or "Interrupt" in exc_name:
                state_snapshot = await agent.aget_state(config)
                async with AsyncSessionLocal() as db:
                    await persist_result(
                        db,
                        bill_id,
                        state_snapshot.values,
                        interrupted=True,
                        tenant_id=tenant_id,
                    )
                logger.info("Agent paused for human review")
                return
            raise
    except Exception as exc:
        logger.exception("Agent run failed")
        async with AsyncSessionLocal() as db:
            freight_bill = await get_bill(db, bill_id, tenant_id)
            if freight_bill:
                freight_bill.status = FreightBillStatus.awaiting_review
                freight_bill.decision_reason = f"Agent error: {exc}"
                freight_bill.processing_completed_at = datetime.utcnow()
                db.add(
                    AuditLog(
                        tenant_id=tenant_id,
                        freight_bill_id=bill_id,
                        event="agent_error",
                        detail={"error": str(exc), "correlation_id": correlation_id},
                    )
                )
                await db.commit()
        raise
    finally:
        clear_contextvars()


async def resume_agent_for_bill(
    bill_id: str,
    tenant_id: str,
    thread_id: str,
    reviewer_decision: str,
    reviewer_notes: str | None,
    correlation_id: str,
    task_id: str | None = None,
) -> None:
    """Resume a durable interrupted thread after a reviewer decision."""
    clear_contextvars()
    bind_contextvars(
        correlation_id=correlation_id,
        freight_bill_id=bill_id,
        tenant_id=tenant_id,
        celery_task_id=task_id,
    )
    config = {"configurable": {"thread_id": thread_id}}
    logger.info("Agent resume started", extra={"reviewer_decision": reviewer_decision})

    try:
        agent = await get_agent()
        await agent.aupdate_state(
            config,
            {"reviewer_decision": reviewer_decision, "reviewer_notes": reviewer_notes or ""},
            as_node="human_review",
        )
        async for _ in agent.astream(None, config=config):
            pass
        state_snapshot = await agent.aget_state(config)
        async with AsyncSessionLocal() as db:
            await persist_result(
                db,
                bill_id,
                state_snapshot.values,
                interrupted=False,
                tenant_id=tenant_id,
            )
        logger.info("Agent resume completed")
    except Exception:
        logger.exception("Agent resume failed")
        raise
    finally:
        clear_contextvars()
