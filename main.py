"""
FastAPI Application
====================
Endpoints:
  POST /freight-bills          — ingest a freight bill, trigger agent
  GET  /freight-bills/{id}     — get bill state, decision, evidence
  GET  /review-queue           — bills waiting for human review
  POST /review/{id}            — submit reviewer decision, resume agent
  GET  /health                 — liveness check
  GET  /metrics                — agent performance summary (bonus observability)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db, engine
from app.models.db_models import Base, FreightBill, FreightBillStatus, AuditLog, Carrier, CarrierContract, Shipment, BillOfLading
from app.services.graph_service import get_graph_service
from app.agent.agent import get_agent

logger = logging.getLogger(__name__)
settings = get_settings()


def _map_decision_to_status(decision: str | None) -> FreightBillStatus:
    value = (decision or "").strip().lower()
    if value in {"auto_approve", "approve", "approved"}:
        return FreightBillStatus.approved
    if value in {"dispute", "disputed"}:
        return FreightBillStatus.disputed
    if value in {"reject", "rejected"}:
        return FreightBillStatus.rejected
    return FreightBillStatus.awaiting_review

# ── App setup ─────────────────────────────────────────────────────────────────

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


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Build in-memory graph from DB
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        graph_service = get_graph_service()
        await graph_service.build(db)
        logger.info("Graph built successfully")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

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
    reviewer_decision: str          # "approve" | "dispute" | "modify"
    reviewer_notes: str | None = None


class FreightBillOut(BaseModel):
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

    class Config:
        from_attributes = True


# ── Background: run agent ─────────────────────────────────────────────────────

async def run_agent_for_bill(bill_id: str, bill_dict: dict):
    """
    Run the LangGraph agent asynchronously.
    Writes results back to Postgres when done (or on interrupt).
    """
    from app.db.session import AsyncSessionLocal

    agent = get_agent()
    thread_id = f"thread-{bill_id}"
    config = {"configurable": {"thread_id": thread_id}}

    graph_service = get_graph_service()

    # Register freight bill in graph for cross-referencing
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
        fb = await db.get(FreightBill, bill_id)
        if fb:
            fb.status = FreightBillStatus.processing
            fb.thread_id = thread_id
            await db.commit()

    try:
        # Stream events — agent runs until END or interrupt
        final_state = None
        async for event in agent.astream(initial_state, config=config):
            logger.info(f"[{bill_id}] agent event: {list(event.keys())}")
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    continue
                final_state = node_output

        state_snapshot = agent.get_state(config)
        interrupted = bool(getattr(state_snapshot, "next", None))
        if interrupted:
            logger.info(f"[{bill_id}] Agent paused for human review")
        await _persist_agent_result(bill_id, state_snapshot.values, interrupted=interrupted)

    except Exception as e:
        # LangGraph raises GraphInterrupt when interrupt() is called
        if "GraphInterrupt" in type(e).__name__ or "Interrupt" in type(e).__name__:
            logger.info(f"[{bill_id}] Agent paused for human review")
            state_snapshot = agent.get_state(config)
            await _persist_agent_result(bill_id, state_snapshot.values, interrupted=True)
        else:
            logger.exception(f"[{bill_id}] Agent error: {e}")
            async with AsyncSessionLocal() as db:
                fb = await db.get(FreightBill, bill_id)
                if fb:
                    fb.status = FreightBillStatus.awaiting_review
                    fb.decision_reason = f"Agent error: {str(e)}"
                    await db.commit()


async def _persist_agent_result(bill_id: str, state: dict, interrupted: bool):
    """Write agent findings, decision, and status back to Postgres."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        fb = await db.get(FreightBill, bill_id)
        if not fb:
            return

        findings = state.get("findings", [])
        decision = state.get("reviewer_decision") or state.get("decision")
        confidence = state.get("confidence", 0.0)
        explanation = state.get("explanation", "")
        audit_events = state.get("audit", [])

        fb.confidence_score = confidence
        fb.decision = decision
        fb.decision_reason = explanation
        fb.evidence = {
            "findings": findings,
            "chosen_contract": state.get("chosen_contract"),
            "ambiguity_note": state.get("ambiguity_note"),
            "shipment": state.get("shipment"),
            "bols_count": len(state.get("bols", [])),
            "prior_billed_weight": state.get("prior_billed_weight", 0),
        }

        if interrupted:
            fb.status = FreightBillStatus.awaiting_review
        else:
            fb.status = _map_decision_to_status(decision)

        # Write audit entries
        for ev in audit_events:
            db.add(AuditLog(
                freight_bill_id=bill_id,
                event=ev.get("event", "unknown"),
                detail=ev,
            ))

        await db.commit()
        logger.info(f"[{bill_id}] Persisted: status={fb.status}, confidence={confidence:.2f}, decision={decision}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/freight-bills", status_code=202)
async def ingest_freight_bill(
    payload: FreightBillIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a freight bill and trigger the agent asynchronously.
    Returns immediately with 202 Accepted; poll GET /freight-bills/{id} for status.
    """
    bill_id = payload.id or f"FB-{uuid.uuid4().hex[:8].upper()}"

    # Check if already exists
    existing = await db.get(FreightBill, bill_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Freight bill {bill_id} already exists")

    # Persist the bill
    fb = FreightBill(
        id=bill_id,
        carrier_id=payload.carrier_id,
        carrier_name=payload.carrier_name,
        bill_number=payload.bill_number,
        bill_date=payload.bill_date,
        shipment_reference=payload.shipment_reference,
        lane=payload.lane,
        billed_weight_kg=payload.billed_weight_kg,
        rate_per_kg=payload.rate_per_kg,
        billing_unit=payload.billing_unit,
        base_charge=payload.base_charge,
        fuel_surcharge=payload.fuel_surcharge,
        gst_amount=payload.gst_amount,
        total_amount=payload.total_amount,
        status=FreightBillStatus.pending,
    )
    db.add(fb)
    db.add(AuditLog(freight_bill_id=bill_id, event="bill_ingested", detail={"source": "api"}))
    await db.commit()

    # Run agent in background
    bill_dict = payload.model_dump()
    bill_dict["id"] = bill_id
    background_tasks.add_task(run_agent_for_bill, bill_id, bill_dict)

    return {"id": bill_id, "status": "processing", "message": "Bill ingested — agent processing started"}


@app.get("/freight-bills/{bill_id}", response_model=FreightBillOut)
async def get_freight_bill(bill_id: str, db: AsyncSession = Depends(get_db)):
    fb = await db.get(FreightBill, bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail=f"Freight bill {bill_id} not found")
    return fb


@app.get("/freight-bills")
async def list_freight_bills(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FreightBill).order_by(FreightBill.created_at.desc()))
    bills = result.scalars().all()
    return [
        {
            "id": fb.id,
            "carrier_name": fb.carrier_name,
            "bill_number": fb.bill_number,
            "lane": fb.lane,
            "total_amount": fb.total_amount,
            "status": fb.status,
            "confidence_score": fb.confidence_score,
            "decision": fb.decision,
        }
        for fb in bills
    ]


@app.get("/review-queue")
async def review_queue(db: AsyncSession = Depends(get_db)):
    """List freight bills currently awaiting human review."""
    result = await db.execute(
        select(FreightBill)
        .where(FreightBill.status == FreightBillStatus.awaiting_review)
        .order_by(FreightBill.created_at.asc())
    )
    bills = result.scalars().all()
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


@app.post("/review/{bill_id}")
async def submit_review(
    bill_id: str,
    payload: ReviewDecisionIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a human reviewer decision to resume the paused agent.
    The agent's interrupt() call returns with this payload.
    """
    fb = await db.get(FreightBill, bill_id)
    if not fb:
        raise HTTPException(status_code=404, detail=f"Freight bill {bill_id} not found")

    if fb.status != FreightBillStatus.awaiting_review:
        raise HTTPException(
            status_code=400,
            detail=f"Bill {bill_id} is not in awaiting_review state (current: {fb.status})"
        )

    if not fb.thread_id:
        raise HTTPException(status_code=500, detail="No thread_id found — cannot resume agent")

    # Update reviewer fields immediately
    fb.reviewer_decision = payload.reviewer_decision
    fb.reviewer_notes = payload.reviewer_notes
    fb.reviewed_at = datetime.utcnow()
    fb.status = FreightBillStatus.processing
    db.add(AuditLog(
        freight_bill_id=bill_id,
        event="reviewer_decision_submitted",
        detail={"decision": payload.reviewer_decision, "notes": payload.reviewer_notes},
    ))
    await db.commit()

    # Resume agent in background
    background_tasks.add_task(resume_agent, bill_id, fb.thread_id, payload.reviewer_decision, payload.reviewer_notes)

    return {"id": bill_id, "message": "Review submitted — agent resuming"}


async def resume_agent(bill_id: str, thread_id: str, reviewer_decision: str, reviewer_notes: str | None):
    """Resume the paused LangGraph agent with reviewer input."""
    agent = get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # update_state injects the reviewer input as the return value of interrupt()
        agent.update_state(
            config,
            {"reviewer_decision": reviewer_decision, "reviewer_notes": reviewer_notes or ""},
            as_node="human_review",
        )

        # Resume from where we left off
        async for event in agent.astream(None, config=config):
            logger.info(f"[{bill_id}] resume event: {list(event.keys())}")

        state_snapshot = agent.get_state(config)
        await _persist_agent_result(bill_id, state_snapshot.values, interrupted=False)

    except Exception as e:
        logger.exception(f"[{bill_id}] Resume error: {e}")


@app.get("/freight-bills/{bill_id}/audit")
async def get_audit_log(bill_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.freight_bill_id == bill_id)
        .order_by(AuditLog.created_at.asc())
    )
    entries = result.scalars().all()
    return [{"event": e.event, "detail": e.detail, "created_at": e.created_at} for e in entries]


@app.get("/metrics")
async def metrics(db: AsyncSession = Depends(get_db)):
    """Observability endpoint — agent performance summary."""
    result = await db.execute(select(FreightBill))
    all_bills = result.scalars().all()

    total = len(all_bills)
    by_status: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    confidences = []

    for fb in all_bills:
        status_key = fb.status.value if fb.status else "unknown"
        by_status[status_key] = by_status.get(status_key, 0) + 1

        if fb.decision:
            by_decision[fb.decision] = by_decision.get(fb.decision, 0) + 1

        if fb.confidence_score is not None:
            confidences.append(fb.confidence_score)

    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None

    return {
        "total_bills": total,
        "by_status": by_status,
        "by_decision": by_decision,
        "avg_confidence_score": avg_confidence,
        "auto_approve_threshold": settings.auto_approve_threshold,
    }
