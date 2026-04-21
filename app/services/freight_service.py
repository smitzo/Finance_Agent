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

INGEST_ALLOWED_FIELDS = {
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
}


def _map_decision_to_status(decision: str | None) -> FreightBillStatus:
    value = (decision or "").strip().lower()
    if value in {"auto_approve", "approve", "approved"}:
        return FreightBillStatus.approved
    if value in {"dispute", "disputed"}:
        return FreightBillStatus.disputed
    if value in {"reject", "rejected"}:
        return FreightBillStatus.rejected
    return FreightBillStatus.awaiting_review


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
    known_data = {k: v for k, v in bill_data.items() if k in INGEST_ALLOWED_FIELDS}
    extra_data = {k: v for k, v in bill_data.items() if k not in INGEST_ALLOWED_FIELDS}

    fb = FreightBill(**known_data)
    if extra_data:
        fb.evidence = {"payload_extra_fields": extra_data}
        logger.info("[%s] Preserved %d extra payload fields in evidence", known_data.get("id", "unknown"), len(extra_data))
    db.add(fb)
    await db.flush()
    return fb


async def find_duplicate_bill(
    db: AsyncSession,
    bill_number: str,
    carrier_id: str | None,
    carrier_name: str | None,
) -> FreightBill | None:
    """
    Best-effort duplicate detection before invoking the agent:
    1) Prefer exact carrier_id + bill_number match.
    2) Fallback to case-insensitive carrier_name + bill_number when carrier_id is missing.
    """
    if carrier_id:
        result = await db.execute(
            select(FreightBill).where(
                FreightBill.bill_number == bill_number,
                FreightBill.carrier_id == carrier_id,
            )
        )
        duplicate = result.scalars().first()
        if duplicate:
            return duplicate

    normalized_name = (carrier_name or "").strip().lower()
    if normalized_name:
        result = await db.execute(select(FreightBill).where(FreightBill.bill_number == bill_number))
        for row in result.scalars().all():
            if (row.carrier_name or "").strip().lower() == normalized_name:
                return row

    return None


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
    existing_evidence = fb.evidence or {}
    result_evidence = {
        "findings": findings,
        "chosen_contract": state.get("chosen_contract"),
        "ambiguity_note": state.get("ambiguity_note"),
        "shipment": state.get("shipment"),
        "bols_count": len(state.get("bols", [])),
        "prior_billed_weight": state.get("prior_billed_weight", 0),
    }
    fb.evidence = {**existing_evidence, **result_evidence}

    if interrupted:
        fb.status = FreightBillStatus.awaiting_review
    else:
        fb.status = _map_decision_to_status(decision)

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
