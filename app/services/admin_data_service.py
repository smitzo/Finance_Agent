"""Admin-only database cleanup helpers."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    AuditLog,
    BillOfLading,
    Carrier,
    CarrierContract,
    FreightBill,
    Shipment,
)


async def clear_all_data(db: AsyncSession) -> dict[str, int]:
    """Delete all application data while keeping the schema intact."""
    audit_result = await db.execute(delete(AuditLog))
    bill_result = await db.execute(delete(FreightBill))
    bol_result = await db.execute(delete(BillOfLading))
    shipment_result = await db.execute(delete(Shipment))
    contract_result = await db.execute(delete(CarrierContract))
    carrier_result = await db.execute(delete(Carrier))

    await db.commit()
    return {
        "audit_logs": audit_result.rowcount or 0,
        "freight_bills": bill_result.rowcount or 0,
        "bills_of_lading": bol_result.rowcount or 0,
        "shipments": shipment_result.rowcount or 0,
        "carrier_contracts": contract_result.rowcount or 0,
        "carriers": carrier_result.rowcount or 0,
    }
