"""
Freight Service
===============
Service layer for freight bill database operations.
Keeps route handlers thin — all DB logic lives here.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import FreightBill, FreightBillStatus, AuditLog

logger = logging.getLogger(__name__)


async def get_bill(db: AsyncSession, bill_id: str) -> FreightBill | None:
    return await db.get(FreightBill, bill_id)


async def list_bills(db: AsyncSession) -> list[FreightBill]:
    result = await db.execute(
        select(FreightBill).order_by(FreightBill.created_at.desc())
    )
    return result.scalars().all()


async def list_review_queue(db: AsyncSession) -> list[FreightBill]:
    result = await db.execute(
        select(FreightBill)
        .where(FreightBill.status == FreightBillStatus.awaiting_review)
        .order_by(FreightBill.created_at.asc())
    )
    return result.scalars().all()


async def create_bill(db: AsyncSession, bill_data: dict) -> FreightBill:
    fb = FreightBill(**bill_data)
    db.add(fb)
    await db.flush()
    return fb


async def set_processing(db: AsyncSession, bill_id: str, thread_id: str) -> None:
    fb = await db.get(FreightBill, bill_id)
    if fb:
        fb.status = FreightBillStatus.processing
        fb.thread_id = thread_id
        await db.commit()


async def persist_result(
    db: AsyncSession,
    bill_id: str,
    state: dict,
    interrupted: bool,
) -> None:
    """Write agent findings, decision, confidence and status back to Postgres."""
    fb = await db.get(FreightBill, bill_id)
    if not fb:
        logger.warning(f"persist_result: bill {bill_id} not found")
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
    elif decision == "auto_approve":
        fb.status = FreightBillStatus.approved
    elif decision == "dispute":
        fb.status = FreightBillStatus.disputed
    else:
        fb.status = FreightBillStatus.awaiting_review

    for ev in audit_events:
        db.add(AuditLog(
            freight_bill_id=bill_id,
            event=ev.get("event", "unknown"),
            detail=ev,
        ))

    await db.commit()
    logger.info(f"[{bill_id}] Persisted: status={fb.status}, confidence={confidence:.2f}, decision={decision}")


async def apply_reviewer_decision(
    db: AsyncSession,
    bill_id: str,
    reviewer_decision: str,
    reviewer_notes: str | None,
) -> FreightBill:
    fb = await db.get(FreightBill, bill_id)
    if not fb:
        raise ValueError(f"Bill {bill_id} not found")

    fb.reviewer_decision = reviewer_decision
    fb.reviewer_notes = reviewer_notes
    fb.reviewed_at = datetime.utcnow()
    fb.status = FreightBillStatus.processing

    db.add(AuditLog(
        freight_bill_id=bill_id,
        event="reviewer_decision_submitted",
        detail={"decision": reviewer_decision, "notes": reviewer_notes},
    ))
    await db.commit()
    return fb


async def get_audit_entries(db: AsyncSession, bill_id: str) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.freight_bill_id == bill_id)
        .order_by(AuditLog.created_at.asc())
    )
    return result.scalars().all()


async def get_metrics(db: AsyncSession) -> dict:
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

    return {
        "total_bills": total,
        "by_status": by_status,
        "by_decision": by_decision,
        "avg_confidence_score": round(sum(confidences) / len(confidences), 3) if confidences else None,
    }