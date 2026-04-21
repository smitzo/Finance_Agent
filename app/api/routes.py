"""
API Routes
==========
HTTP endpoints for freight bill ingestion, review, and observability.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import get_agent
from app.db.session import AsyncSessionLocal, get_db
from app.models.db_models import AuditLog, FreightBillStatus
from app.services.freight_service import (
    apply_reviewer_decision,
    create_bill,
    get_audit_entries,
    get_bill,
    get_metrics,
    list_bills,
    list_review_queue,
    persist_result,
)
from app.services.graph_service import get_graph_service

logger = logging.getLogger(__name__)

router = APIRouter()


class FreightBillIn(BaseModel):
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

    try:
        async for _ in agent.astream(initial_state, config=config):
            pass
        state_snapshot = agent.get_state(config)
        interrupted = bool(getattr(state_snapshot, "next", None))
        if interrupted:
            logger.info("[%s] Agent paused for human review", bill_id)
        async with AsyncSessionLocal() as db:
            await persist_result(db, bill_id, state_snapshot.values, interrupted=interrupted)
    except Exception as exc:
        exc_name = type(exc).__name__
        if "GraphInterrupt" in exc_name or "Interrupt" in exc_name:
            logger.info("[%s] Agent paused for human review", bill_id)
            state_snapshot = agent.get_state(config)
            async with AsyncSessionLocal() as db:
                await persist_result(db, bill_id, state_snapshot.values, interrupted=True)
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


@router.post("/freight-bills", status_code=202)
async def ingest_freight_bill(
    payload: FreightBillIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    bill_id = payload.id or f"FB-{uuid.uuid4().hex[:8].upper()}"
    if await get_bill(db, bill_id):
        raise HTTPException(status_code=409, detail=f"Freight bill {bill_id} already exists")

    bill_data = payload.model_dump()
    bill_data["id"] = bill_id
    await create_bill(db, bill_data)
    db.add(AuditLog(freight_bill_id=bill_id, event="bill_ingested", detail={"source": "api"}))
    await db.commit()

    background_tasks.add_task(run_agent_for_bill, bill_id, bill_data)
    return {"id": bill_id, "status": "processing", "message": "Bill ingested — agent processing started"}


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
