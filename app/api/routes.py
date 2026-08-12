"""
API Routes: HTTP endpoints for freight bill ingestion, review, and observability.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser, require_admin, require_current_user
from app.db.session import get_db
from app.models.db_models import AuditLog, Company, PartnerFirm, FreightBillStatus
from app.observability import current_correlation_id
from app.tenancy import tenant_from_header
from app.workflows import FREIGHT_AUDIT, SUPPORTED_WORKFLOWS, is_supported_workflow
from app.services.admin_data_service import clear_all_data
from app.services.demo_data_service import clear_demo_data, load_demo_data
from app.services.freight_service import (
    apply_reviewer_decision,
    create_bill,
    find_by_idempotency_key,
    find_duplicate_bill,
    get_audit_entries,
    get_bill,
    get_metrics,
    list_bills,
    list_review_queue,
)
from app.services.graph_service import get_graph_service
from app.worker.tasks import enqueue_bill, enqueue_review_resume

logger = logging.getLogger(__name__)
router = APIRouter()


class FreightBillIn(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    workflow_type: str = Field(default=FREIGHT_AUDIT, min_length=1, max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=100)
    carrier_id: str | None = None
    carrier_name: str = Field(min_length=1, max_length=200)
    bill_number: str = Field(min_length=1, max_length=100)
    bill_date: str = Field(min_length=10, max_length=20)
    shipment_reference: str | None = None
    lane: str = Field(min_length=3, max_length=30)
    billed_weight_kg: float = Field(gt=0)
    rate_per_kg: float | None = Field(default=None, gt=0)
    billing_unit: str = Field(default="kg", min_length=1, max_length=20)
    base_charge: float = Field(ge=0)
    fuel_surcharge: float = Field(ge=0)
    gst_amount: float = Field(ge=0)
    total_amount: float = Field(gt=0)


class ReviewDecisionIn(BaseModel):
    reviewer_decision: Literal["approve", "dispute", "reject"]
    reviewer_notes: str | None = None


class FreightBillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    workflow_type: str
    idempotency_key: str | None
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


class PartnerFirmOut(BaseModel):
    id: str
    name: str
    firm_type: str
    registration_number: str | None
    gstin: str | None
    contact_name: str
    contact_email: str
    contact_phone: str | None
    status: str


class CompanyOut(BaseModel):
    id: str
    tenant_id: str
    legal_name: str
    display_name: str
    gstin: str | None
    country: str
    timezone: str
    billing_email: str
    status: str
    ca_partner_firm: PartnerFirmOut | None


class CompanyUpsertIn(BaseModel):
    legal_name: str = Field(min_length=2, max_length=200)
    display_name: str = Field(min_length=2, max_length=160)
    gstin: str | None = Field(default=None, max_length=20)
    country: str = Field(default="IN", min_length=2, max_length=2)
    timezone: str = Field(default="Asia/Kolkata", max_length=60)
    billing_email: str = Field(min_length=3, max_length=200)


class PartnerFirmUpsertIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=80)
    gstin: str | None = Field(default=None, max_length=20)
    contact_name: str = Field(min_length=2, max_length=120)
    contact_email: str = Field(min_length=3, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=40)


class SessionOut(BaseModel):
    username: str
    role: str
    tenant_id: str
    is_demo: bool


async def _ingest_one_bill(
    payload: FreightBillIn,
    db: AsyncSession,
    tenant_id: str,
    queue_agent: bool = True,
) -> dict:
    bill_id = payload.id or f"FB-{uuid.uuid4().hex[:8].upper()}"

    if await get_bill(db, bill_id, tenant_id):
        return {
            "id": bill_id,
            "accepted": False,
            "status": "duplicate_id",
            "error": f"Freight bill {bill_id} already exists",
        }

    bill_data = payload.model_dump()
    bill_data["id"] = bill_id
    bill_data["tenant_id"] = tenant_id
    if not is_supported_workflow(bill_data["workflow_type"]):
        return {
            "id": bill_id,
            "accepted": False,
            "status": "unsupported_workflow",
            "error": (
                f"Unsupported workflow_type '{bill_data['workflow_type']}'. "
                f"Supported workflows: {sorted(SUPPORTED_WORKFLOWS)}"
            ),
        }

    existing_idempotent_bill = await find_by_idempotency_key(
        db,
        tenant_id=tenant_id,
        workflow_type=bill_data["workflow_type"],
        idempotency_key=bill_data.get("idempotency_key"),
    )
    if existing_idempotent_bill:
        return {
            "id": existing_idempotent_bill.id,
            "accepted": True,
            "status": existing_idempotent_bill.status.value if existing_idempotent_bill.status else "unknown",
            "message": "Idempotent request already accepted",
        }

    duplicate = await find_duplicate_bill(
        db=db,
        tenant_id=tenant_id,
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
        "workflow_type",
        "idempotency_key",
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
        "tenant_id",
    })
    logger.info("[%s] Ingest request received (extra_keys=%s)", bill_id, extra_keys)

    correlation_id = current_correlation_id()
    freight_bill = await create_bill(db, bill_data, tenant_id)
    freight_bill.correlation_id = correlation_id
    db.add(AuditLog(
        tenant_id=tenant_id,
        freight_bill_id=bill_id,
        event="bill_ingested",
        detail={"source": "api", "correlation_id": correlation_id},
    ))
    await db.commit()

    if queue_agent:
        freight_bill.celery_task_id = enqueue_bill(bill_id, bill_data, correlation_id)
        await db.commit()
    return {
        "id": bill_id,
        "accepted": True,
        "status": "pending",
        "message": "Bill ingested and queued for agent processing",
        "_bill_data": bill_data,
        "_correlation_id": correlation_id,
    }


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/graph")
async def health_graph() -> dict:
    graph_service = get_graph_service()
    result = await graph_service.health()
    return {**result, "timestamp": datetime.utcnow().isoformat()}


@router.get("/session", response_model=SessionOut, tags=["Authentication"])
async def current_session(
    tenant_id: str = Depends(tenant_from_header),
    user: AuthenticatedUser = Depends(require_current_user),
) -> SessionOut:
    return SessionOut(
        username=user.username,
        role=user.role,
        tenant_id=tenant_id,
        is_demo=user.role == "demo_admin",
    )


@router.get("/workflows")
async def list_workflows() -> list[dict]:
    return [
        {
            "name": workflow.name,
            "description": workflow.description,
            "agent": workflow.agent,
        }
        for workflow in SUPPORTED_WORKFLOWS.values()
    ]


@router.get("/company", response_model=CompanyOut | None)
async def get_company_profile(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> CompanyOut | None:
    result = await db.execute(
        select(Company)
        .where(Company.tenant_id == tenant_id, Company.status == "active")
        .order_by(Company.created_at.asc())
    )
    company = result.scalars().first()
    if not company:
        return None

    partner = None
    if company.ca_partner_firm_id:
        partner_row = await db.get(PartnerFirm, company.ca_partner_firm_id)
        if partner_row and partner_row.tenant_id == tenant_id:
            partner = PartnerFirmOut(
                id=partner_row.id,
                name=partner_row.name,
                firm_type=partner_row.firm_type,
                registration_number=partner_row.registration_number,
                gstin=partner_row.gstin,
                contact_name=partner_row.contact_name,
                contact_email=partner_row.contact_email,
                contact_phone=partner_row.contact_phone,
                status=partner_row.status,
            )

    return CompanyOut(
        id=company.id,
        tenant_id=company.tenant_id,
        legal_name=company.legal_name,
        display_name=company.display_name,
        gstin=company.gstin,
        country=company.country,
        timezone=company.timezone,
        billing_email=company.billing_email,
        status=company.status,
        ca_partner_firm=partner,
    )


@router.put("/company", response_model=CompanyOut)
async def upsert_company_profile(
    payload: CompanyUpsertIn,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> CompanyOut:
    result = await db.execute(
        select(Company).where(Company.tenant_id == tenant_id).order_by(Company.created_at.asc())
    )
    company = result.scalars().first()
    if company is None:
        company = Company(id=f"COM-{uuid.uuid4().hex[:10].upper()}", tenant_id=tenant_id)
        db.add(company)
    for field, value in payload.model_dump().items():
        setattr(company, field, value)
    company.status = "active"
    await db.commit()
    await db.refresh(company)
    return CompanyOut(
        id=company.id,
        tenant_id=company.tenant_id,
        legal_name=company.legal_name,
        display_name=company.display_name,
        gstin=company.gstin,
        country=company.country,
        timezone=company.timezone,
        billing_email=company.billing_email,
        status=company.status,
        ca_partner_firm=None,
    )


@router.get("/partner-firms", response_model=list[PartnerFirmOut])
async def list_partner_firms(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> list[PartnerFirmOut]:
    result = await db.execute(
        select(PartnerFirm)
        .where(PartnerFirm.tenant_id == tenant_id)
        .order_by(PartnerFirm.created_at.asc())
    )
    return [
        PartnerFirmOut(
            id=firm.id,
            name=firm.name,
            firm_type=firm.firm_type,
            registration_number=firm.registration_number,
            gstin=firm.gstin,
            contact_name=firm.contact_name,
            contact_email=firm.contact_email,
            contact_phone=firm.contact_phone,
            status=firm.status,
        )
        for firm in result.scalars().all()
    ]


@router.post("/partner-firms", response_model=PartnerFirmOut)
async def upsert_partner_firm(
    payload: PartnerFirmUpsertIn,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> PartnerFirmOut:
    result = await db.execute(
        select(PartnerFirm).where(
            PartnerFirm.tenant_id == tenant_id,
            PartnerFirm.name == payload.name,
        )
    )
    partner = result.scalars().first()
    if partner is None:
        partner = PartnerFirm(
            id=f"PF-{uuid.uuid4().hex[:10].upper()}",
            tenant_id=tenant_id,
            firm_type="ca_firm",
        )
        db.add(partner)
    for field, value in payload.model_dump().items():
        setattr(partner, field, value)
    partner.status = "active"
    await db.commit()
    await db.refresh(partner)
    return PartnerFirmOut(
        id=partner.id,
        name=partner.name,
        firm_type=partner.firm_type,
        registration_number=partner.registration_number,
        gstin=partner.gstin,
        contact_name=partner.contact_name,
        contact_email=partner.contact_email,
        contact_phone=partner.contact_phone,
        status=partner.status,
    )


@router.post("/admin/rebuild-graph", tags=["Admin"], summary="Rebuild in-memory graph")
async def rebuild_graph(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    graph_service = get_graph_service()
    await graph_service.build(db, tenant_id)
    return {"status": "ok", "tenant_id": tenant_id, "message": "Graph rebuilt from database"}


@router.post("/admin/demo/load", status_code=202, tags=["Admin"], summary="Load and process demo data")
async def load_and_process_demo_data(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    result = await load_demo_data(db, tenant_id)

    graph_service = get_graph_service()
    await graph_service.build(db, tenant_id)

    correlation_id = current_correlation_id()
    for bill_data in result["bill_payloads"]:
        task_id = enqueue_bill(bill_data["id"], bill_data, correlation_id)
        freight_bill = await get_bill(db, bill_data["id"], tenant_id)
        if freight_bill:
            freight_bill.correlation_id = correlation_id
            freight_bill.celery_task_id = task_id
    await db.commit()

    return {
        "status": "processing",
        "message": (
            f"Demo data loaded and {len(result['bill_payloads'])} freight bills queued. "
            "Open logs/app.log to watch deterministic and LLM paths."
        ),
        "loaded": result["loaded"],
        "removed_before_load": result["removed"],
        "deterministic_bill_ids": [
            item["bill_id"] for item in result["bill_scenarios"]
            if item["category"] == "deterministic"
        ],
        "llm_bill_ids": [
            item["bill_id"] for item in result["bill_scenarios"]
            if item["category"] == "llm"
        ],
        "edge_case_bill_ids": [
            item["bill_id"] for item in result["bill_scenarios"]
            if item["category"] == "edge"
        ],
        "scenario_catalog": result["bill_scenarios"],
    }


@router.delete("/admin/demo", tags=["Admin"], summary="Remove demo data")
async def remove_demo_data(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    removed = await clear_demo_data(db, tenant_id)
    graph_service = get_graph_service()
    await graph_service.build(db, tenant_id)
    return {
        "status": "ok",
        "message": "Demo data removed. Seed and non-demo records were not touched.",
        "removed": removed,
    }


@router.delete("/admin/data", tags=["Admin"], summary="Remove all application data")
async def remove_all_data(
    confirm: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_admin),
) -> dict:
    if confirm != "DELETE_ALL":
        raise HTTPException(
            status_code=400,
            detail="Pass confirm=DELETE_ALL to delete all application data.",
        )

    removed = await clear_all_data(db, tenant_id)
    graph_service = get_graph_service()
    await graph_service.build(db, tenant_id)
    return {
        "status": "ok",
        "message": "All application data removed. Database schema remains intact.",
        "removed": removed,
    }


@router.post("/freight-bills", status_code=202)
async def ingest_freight_bill(
    payload: FreightBillIn | list[FreightBillIn],
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> dict:
    # Backward-compatible single ingest
    if isinstance(payload, FreightBillIn):
        result = await _ingest_one_bill(payload, db, tenant_id)
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
    accepted_bill_items: list[dict] = []
    for item in payload:
        try:
            result = await _ingest_one_bill(item, db, tenant_id, queue_agent=False)
            if result.get("accepted") and result.get("_bill_data"):
                accepted_bill_items.append({
                    "bill": result["_bill_data"],
                    "correlation_id": result["_correlation_id"],
                })
            result.pop("_bill_data", None)
            result.pop("_correlation_id", None)
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
    for item in accepted_bill_items:
        bill_data = item["bill"]
        task_id = enqueue_bill(bill_data["id"], bill_data, item["correlation_id"])
        freight_bill = await get_bill(db, bill_data["id"], tenant_id)
        if freight_bill:
            freight_bill.celery_task_id = task_id
    if accepted_bill_items:
        await db.commit()
    return {
        "total": len(results),
        "accepted": accepted,
        "rejected": rejected,
        "items": results,
    }


@router.get("/freight-bills/{bill_id}", response_model=FreightBillOut)
async def get_freight_bill(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> FreightBillOut:
    fb = await get_bill(db, bill_id, tenant_id)
    if not fb:
        raise HTTPException(status_code=404, detail=f"Freight bill {bill_id} not found")
    return FreightBillOut(
        id=fb.id,
        tenant_id=fb.tenant_id,
        workflow_type=fb.workflow_type,
        idempotency_key=fb.idempotency_key,
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
async def list_freight_bills(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: AuthenticatedUser = Depends(require_current_user),
) -> list[dict]:
    bills = await list_bills(db, tenant_id, limit=limit, offset=offset)
    return [
        {
            "id": fb.id,
            "tenant_id": fb.tenant_id,
            "workflow_type": fb.workflow_type,
            "carrier_name": fb.carrier_name,
            "bill_number": fb.bill_number,
            "bill_date": fb.bill_date,
            "lane": fb.lane,
            "total_amount": fb.total_amount,
            "status": fb.status.value if fb.status else "unknown",
            "confidence_score": fb.confidence_score,
            "decision": fb.decision,
            "decision_reason": fb.decision_reason,
            "created_at": fb.created_at,
        }
        for fb in bills
    ]


@router.get("/review-queue")
async def review_queue(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _: AuthenticatedUser = Depends(require_current_user),
) -> list[dict]:
    bills = await list_review_queue(db, tenant_id, limit=limit, offset=offset)
    return [
        {
            "id": fb.id,
            "tenant_id": fb.tenant_id,
            "workflow_type": fb.workflow_type,
            "carrier_name": fb.carrier_name,
            "bill_number": fb.bill_number,
            "bill_date": fb.bill_date,
            "lane": fb.lane,
            "total_amount": fb.total_amount,
            "status": fb.status.value if fb.status else "unknown",
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
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> dict:
    fb = await get_bill(db, bill_id, tenant_id)
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
        tenant_id=tenant_id,
    )
    logger.info("[%s] Reviewer decision submitted (%s)", bill_id, payload.reviewer_decision)
    correlation_id = current_correlation_id()
    updated.correlation_id = correlation_id
    updated.celery_task_id = enqueue_review_resume(
        bill_id,
        tenant_id,
        updated.thread_id or "",
        payload.reviewer_decision,
        payload.reviewer_notes,
        correlation_id,
    )
    await db.commit()
    return {"id": bill_id, "message": "Review submitted and queued for agent resume"}


@router.get("/freight-bills/{bill_id}/audit")
async def get_audit_log(
    bill_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> list[dict]:
    entries = await get_audit_entries(db, bill_id, tenant_id)
    return [{"event": e.event, "detail": e.detail, "created_at": e.created_at} for e in entries]


@router.get("/metrics")
async def metrics(
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(tenant_from_header),
    _: AuthenticatedUser = Depends(require_current_user),
) -> dict:
    return await get_metrics(db, tenant_id)
