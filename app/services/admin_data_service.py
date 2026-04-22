"""Admin-only database cleanup helpers."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy import normalize_tenant_id
from app.models.db_models import (
    AuditLog,
    BillOfLading,
    Carrier,
    CarrierContract,
    FreightBill,
    Shipment,
)


async def clear_all_data(db: AsyncSession, tenant_id: str | None = None) -> dict[str, int]:
    """Delete one tenant's application data while keeping the schema intact."""
    tenant_id = normalize_tenant_id(tenant_id)
    audit_result = await db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
    bill_result = await db.execute(delete(FreightBill).where(FreightBill.tenant_id == tenant_id))
    bol_result = await db.execute(delete(BillOfLading).where(BillOfLading.tenant_id == tenant_id))
    shipment_result = await db.execute(delete(Shipment).where(Shipment.tenant_id == tenant_id))
    contract_result = await db.execute(delete(CarrierContract).where(CarrierContract.tenant_id == tenant_id))
    carrier_result = await db.execute(delete(Carrier).where(Carrier.tenant_id == tenant_id))

    await db.commit()
    return {
        "tenant_id": tenant_id,
        "audit_logs": audit_result.rowcount or 0,
        "freight_bills": bill_result.rowcount or 0,
        "bills_of_lading": bol_result.rowcount or 0,
        "shipments": shipment_result.rowcount or 0,
        "carrier_contracts": contract_result.rowcount or 0,
        "carriers": carrier_result.rowcount or 0,
    }
