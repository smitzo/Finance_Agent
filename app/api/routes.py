"""
API Routes: HTTP endpoints for freight bill ingestion, review, and observability.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import get_agent
from app.config import get_settings
from app.db.session import AsyncSessionLocal, get_db
from app.models.db_models import AuditLog, FreightBillStatus
from app.services.admin_data_service import clear_all_data
from app.services.demo_data_service import clear_demo_data, load_demo_data
from app.services.freight_service import (
    apply_reviewer_decision,
    create_bill,
    find_duplicate_bill,
    get_audit_entries,
    get_bill,
    get_metrics,
    list_bills,
    list_review_queue,
    persist_result,
)
from app.services.graph_service import get_graph_service

logger = logging.getLogger(__name__)
settings = get_settings()
_agent_run_semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_agent_runs))

router = APIRouter()


class FreightBillIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    carrier_id: str | None = None
    carrier_name: str
    bill_number: str
    bill_date: str
    shipment_reference: str | None = None
    lane: str
    billed_weight_kg: float
    rate_per_kg: float | None = None
    billing_unit: str = "kg"
    base_charge: float
    fuel_surcharge: float
    gst_amount: float
    total_amount: float


class ReviewDecisionIn(BaseModel):
    reviewer_decision: str
    reviewer_notes: str | None = None


class FreightBillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    carrier_name: str
    bill_number: str
    bill_date: str
    lane: str
    total_amount: float
    status: str
    confidence_score: float | None
    decision: str | None
    decision_reason: str | None
    evidence: Any | None
    reviewer_decision: str | None
    reviewer_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime


async def run_agent_for_bill(bill_id: str, bill_dict: dict) -> None:
    """Run the LangGraph agent and persist the final or interrupted state."""
    logger.info("[%s] Agent run queued", bill_id)
    async with _agent_run_semaphore:
        logger.info("[%s] Agent run started", bill_id)
        agent = get_agent()
        thread_id = f"thread-{bill_id}"
        config = {"configurable": {"thread_id": thread_id}}

        graph_service = get_graph_service()
        graph_service.add_freight_bill(bill_id, {**bill_dict, "id": bill_id})

        initial_state = {
            "bill": bill_dict,
            "bill_id": bill_id,
            "carrier": None,
            "carrier_id": bill_dict.get("carrier_id"),
            "all_candidate_contracts": [],
            "chosen_contract": None,
            "shipment": None,
            "bols": [],
            "prior_billed_weight": 0.0,
            "existing_bill_ids": [],
            "findings": [],
            "ambiguity_note": None,
            "confidence": 0.0,
            "decision": None,
            "explanation": None,
            "reviewer_decision": None,
            "reviewer_notes": None,
            "audit": [],
        }

        async with AsyncSessionLocal() as db:
            fb = await get_bill(db, bill_id)
            if fb:
                fb.status = FreightBillStatus.processing
                fb.thread_id = thread_id
                await db.commit()
                logger.info("[%s] Marked bill as processing (thread_id=%s)", bill_id, thread_id)

        try:
            async for _ in agent.astream(initial_state, config=config):
                pass
            state_snapshot = agent.get_state(config)
            interrupted = bool(getattr(state_snapshot, "next", None))
            if interrupted:
                logger.info("[%s] Agent paused for human review", bill_id)
            async with AsyncSessionLocal() as db:
                await persist_result(db, bill_id, state_snapshot.values, interrupted=interrupted)
            logger.info("[%s] Agent run completed (interrupted=%s)", bill_id, interrupted)
        except Exception as exc:
            exc_name = type(exc).__name__
            if "GraphInterrupt" in exc_name or "Interrupt" in exc_name:
                logger.info("[%s] Agent paused for human review", bill_id)
                state_snapshot = agent.get_state(config)
                async with AsyncSessionLocal() as db:
                    await persist_result(db, bill_id, state_snapshot.values, interrupted=True)
            elif (
                isinstance(exc, RuntimeError)
                and "get_configurable outside of a runnable context" in str(exc).lower()
            ):
                # Known compatibility issue seen with some Python/LangGraph combinations
                # around interrupt() in async execution.
                logger.warning(
                    "[%s] Interrupt runtime compatibility issue detected; persisting latest state as awaiting_review",
                    bill_id,
                )
                try:
                    state_snapshot = agent.get_state(config)
                    async with AsyncSessionLocal() as db:
                        await persist_result(db, bill_id, state_snapshot.values, interrupted=True)
                except Exception:
                    logger.exception("[%s] Failed to persist fallback state after interrupt runtime issue", bill_id)
            else:
                logger.exception("[%s] Agent error: %s", bill_id, exc)
                async with AsyncSessionLocal() as db:
                    fb = await get_bill(db, bill_id)
                    if fb:
                        fb.status = FreightBillStatus.awaiting_review
                        fb.decision_reason = f"Agent error: {exc}"
                        db.add(
                            AuditLog(
                                freight_bill_id=bill_id,
                                event="agent_error",
                                detail={"error": str(exc)},
                            )
                        )
                        await db.commit()


async def _ingest_one_bill(
    payload: FreightBillIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> dict:
    bill_id = payload.id or f"FB-{uuid.uuid4().hex[:8].upper()}"

    if await get_bill(db, bill_id):
        return {
            "id": bill_id,
            "accepted": False,
            "status": "duplicate_id",
            "error": f"Freight bill {bill_id} already exists",
        }

    bill_data = payload.model_dump()
    bill_data["id"] = bill_id

    duplicate = await find_duplicate_bill(
        db=db,
        bill_number=bill_data["bill_number"],
        carrier_id=bill_data.get("carrier_id"),
        carrier_name=bill_data.get("carrier_name"),
    )
    if duplicate:
        logger.info(
            "[%s] Duplicate bill detected before agent run (matches existing id=%s)",
            bill_id,
            duplicate.id,
        )
        return {
            "id": bill_id,
            "accepted": False,
            "status": "duplicate_bill",
            "error": (
                f"Duplicate bill_number '{bill_data['bill_number']}' "
                f"for carrier (existing id={duplicate.id})"
            ),
        }
    extra_keys = sorted(set(bill_data.keys()) - {
        "id",
        "carrier_id",
        "carrier_name",
        "bill_number",
        "bill_date",
        "shipment_reference",
        "lane",
        "billed_weight_kg",
        "rate_per_kg",
        "billing_unit",
        "base_charge",
        "fuel_surcharge",
        "gst_amount",
        "total_amount",
    })
    logger.info("[%s] Ingest request received (extra_keys=%s)", bill_id, extra_keys)

    await create_bill(db, bill_data)
    db.add(AuditLog(freight_bill_id=bill_id, event="bill_ingested", detail={"source": "api"}))
    await db.commit()

    background_tasks.add_task(run_agent_for_bill, bill_id, bill_data)
    return {
        "id": bill_id,
        "accepted": True,
        "status": "processing",
        "message": "Bill ingested — agent processing started",
    }


async def resume_agent(
    bill_id: str,
    thread_id: str,
    reviewer_decision: str,
    reviewer_notes: str | None,
) -> None:
    """Resume an interrupted LangGraph thread from the human review node."""
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        agent.update_state(
            config,
            {"reviewer_decision": reviewer_decision, "reviewer_notes": reviewer_notes or ""},
            as_node="human_review",
        )
        async for _ in agent.astream(None, config=config):
            pass
        state_snapshot = agent.get_state(config)
        async with AsyncSessionLocal() as db:
            await persist_result(db, bill_id, state_snapshot.values, interrupted=False)
    except Exception as exc:
        logger.exception("[%s] Resume error: %s", bill_id, exc)


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected", "timestamp": datetime.utcnow().isoformat()}


@router.post("/admin/rebuild-graph", tags=["Admin"], summary="Rebuild in-memory graph")
async def rebuild_graph(db: AsyncSession = Depends(get_db)) -> dict:
    graph_service = get_graph_service()
    await graph_service.build(db)
    return {"status": "ok", "message": "Graph rebuilt from database"}


@router.post("/admin/demo/load", status_code=202, tags=["Admin"], summary="Load and process demo data")
async def load_and_process_demo_data(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await load_demo_data(db)

    graph_service = get_graph_service()
    await graph_service.build(db)

    for bill_data in result["bill_payloads"]:
        background_tasks.add_task(run_agent_for_bill, bill_data["id"], bill_data)

    return {
        "status": "processing",
        "message": (
            "Demo data loaded and 20 freight bills queued. "
            "Open logs/app.log to watch deterministic and LLM paths."
        ),
        "loaded": result["loaded"],
        "removed_before_load": result["removed"],
        "deterministic_bill_ids": [b["id"] for b in result["bill_payloads"] if b["carrier_id"]],
        "llm_bill_ids": [b["id"] for b in result["bill_payloads"] if not b["carrier_id"]],
    }


@router.delete("/admin/demo", tags=["Admin"], summary="Remove demo data")
async def remove_demo_data(db: AsyncSession = Depends(get_db)) -> dict:
    removed = await clear_demo_data(db)
    graph_service = get_graph_service()
    await graph_service.build(db)
    return {
        "status": "ok",
        "message": "Demo data removed. Seed and non-demo records were not touched.",
        "removed": removed,
    }


@router.delete("/admin/data", tags=["Admin"], summary="Remove all application data")
async def remove_all_data(
    confirm: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if confirm != "DELETE_ALL":
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=DELETE_ALL to delete all application data.",
        )

    removed = await clear_all_data(db)
    graph_service = get_graph_service()
    await graph_service.build(db)
    return {
        "status": "ok",
        "message": "All application data removed. Database schema remains intact.",
        "removed": removed,
    }


@router.post("/freight-bills", status_code=202)
async def ingest_freight_bill(
    payload: FreightBillIn | list[FreightBillIn],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Backward-compatible single ingest
    if isinstance(payload, FreightBillIn):
        result = await _ingest_one_bill(payload, background_tasks, db)
        if not result["accepted"]:
            raise HTTPException(status_code=409, detail=result["error"])
        return {
            "id": result["id"],
            "status": result["status"],
            "message": result["message"],
        }

    # Bulk ingest
    if not payload:
        raise HTTPException(status_code=400, detail="Payload list is empty")

    results: list[dict] = []
    for item in payload:
        try:
            result = await _ingest_one_bill(item, background_tasks, db)
            results.append(result)
        except Exception as exc:
            await db.rollback()
            failed_id = item.id or "unknown"
            logger.exception("[%s] Bulk ingest failed: %s", failed_id, exc)
            results.append({
                "id": failed_id,
                "accepted": False,
                "status": "error",
                "error": str(exc),
            })

    accepted = sum(1 for r in results if r.get("accepted"))
    rejected = len(results) - accepted
    return {
        "total": len(results),
        "accepted": accepted,
        "rejected": rejected,
        "items": results,
    }


@router.get("/freight-bills/{bill_id}", response_model=FreightBillOut)
async def get_freight_bill(bill_id: str, db: AsyncSession = Depends(get_db)) -> FreightBillOut:
    fb = await get_bill(db, bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail=f"Freight bill {bill_id} not found")
    return FreightBillOut(
        id=fb.id,
        carrier_name=fb.carrier_name,
        bill_number=fb.bill_number,
        bill_date=fb.bill_date,
        lane=fb.lane,
        total_amount=fb.total_amount,
        status=fb.status.value if fb.status else "unknown",
        confidence_score=fb.confidence_score,
        decision=fb.decision,
        decision_reason=fb.decision_reason,
        evidence=fb.evidence,
        reviewer_decision=fb.reviewer_decision,
        reviewer_notes=fb.reviewer_notes,
        reviewed_at=fb.reviewed_at,
        created_at=fb.created_at,
    )


@router.get("/freight-bills")
async def list_freight_bills(db: AsyncSession = Depends(get_db)) -> list[dict]:
    bills = await list_bills(db)
    return [
        {
            "id": fb.id,
            "carrier_name": fb.carrier_name,
            "bill_number": fb.bill_number,
            "lane": fb.lane,
            "total_amount": fb.total_amount,
            "status": fb.status.value if fb.status else "unknown",
            "confidence_score": fb.confidence_score,
            "decision": fb.decision,
        }
        for fb in bills
    ]


@router.get("/review-queue")
async def review_queue(db: AsyncSession = Depends(get_db)) -> list[dict]:
    bills = await list_review_queue(db)
    return [
        {
            "id": fb.id,
            "carrier_name": fb.carrier_name,
            "bill_number": fb.bill_number,
            "lane": fb.lane,
            "total_amount": fb.total_amount,
            "confidence_score": fb.confidence_score,
            "decision": fb.decision,
            "decision_reason": fb.decision_reason,
            "evidence": fb.evidence,
            "created_at": fb.created_at,
        }
        for fb in bills
    ]


@router.post("/review/{bill_id}")
async def submit_review(
    bill_id: str,
    payload: ReviewDecisionIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    fb = await get_bill(db, bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail=f"Freight bill {bill_id} not found")
    if fb.status != FreightBillStatus.awaiting_review:
        raise HTTPException(
            status_code=400,
            detail=f"Bill {bill_id} is not in awaiting_review state (current: {fb.status})",
        )
    if not fb.thread_id:
        raise HTTPException(status_code=500, detail="No thread_id found — cannot resume agent")

    updated = await apply_reviewer_decision(
        db,
        bill_id=bill_id,
        reviewer_decision=payload.reviewer_decision,
        reviewer_notes=payload.reviewer_notes,
    )
    logger.info("[%s] Reviewer decision submitted (%s)", bill_id, payload.reviewer_decision)
    background_tasks.add_task(
        resume_agent,
        bill_id,
        updated.thread_id or "",
        payload.reviewer_decision,
        payload.reviewer_notes,
    )
    return {"id": bill_id, "message": "Review submitted — agent resuming"}


@router.get("/freight-bills/{bill_id}/audit")
async def get_audit_log(bill_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    entries = await get_audit_entries(db, bill_id)
    return [{"event": e.event, "detail": e.detail, "created_at": e.created_at} for e in entries]


@router.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db)) -> dict:
    return await get_metrics(db)
