"""
Demo data generation and cleanup.

Demo records are deterministic and isolated with DEMO/CAR-DEMO prefixes so they
can be safely loaded, processed, and removed without touching assignment seed
data or user-created bills.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import (
    AuditLog,
    BillOfLading,
    Carrier,
    CarrierContract,
    FreightBill,
    FreightBillStatus,
    Shipment,
)

DEMO_BILL_COUNT = 20
DEMO_DETERMINISTIC_COUNT = 10
DEMO_LLM_COUNT = 10


def _money(value: float) -> float:
    return round(value, 2)


def _bill_amounts(weight: float, rate: float, fsc_percent: float) -> tuple[float, float, float, float]:
    base = _money(weight * rate)
    fsc = _money(base * fsc_percent / 100)
    gst = _money((base + fsc) * 0.18)
    total = _money(base + fsc + gst)
    return base, fsc, gst, total


def build_demo_dataset() -> dict[str, list[dict]]:
    """Build 20 demo freight bills and their reference records."""
    carriers = [
        {
            "id": "CAR-DEMO001",
            "name": "Demo Atlas Freight",
            "carrier_code": "DAT",
            "gstin": "27DEMO0001A1Z1",
            "bank_account": "DEMO-ATLAS-001",
            "status": "active",
            "onboarded_on": "2024-01-01",
        },
        {
            "id": "CAR-DEMO002",
            "name": "Demo Northline Logistics",
            "carrier_code": "DNL",
            "gstin": "27DEMO0002A1Z2",
            "bank_account": "DEMO-NORTH-002",
            "status": "active",
            "onboarded_on": "2024-02-01",
        },
        {
            "id": "CAR-DEMO003",
            "name": "Demo Meridian Transport",
            "carrier_code": "DMT",
            "gstin": "27DEMO0003A1Z3",
            "bank_account": "DEMO-MERIDIAN-003",
            "status": "active",
            "onboarded_on": "2024-03-01",
        },
        {
            "id": "CAR-DEMO004",
            "name": "Demo Skyline Cargo",
            "carrier_code": "DSC",
            "gstin": "27DEMO0004A1Z4",
            "bank_account": "DEMO-SKYLINE-004",
            "status": "active",
            "onboarded_on": "2024-04-01",
        },
    ]

    contracts: list[dict] = []
    shipments: list[dict] = []
    bols: list[dict] = []
    freight_bills: list[dict] = []

    deterministic_lanes = [
        ("DEL-JAI", 9.50, 500, "CAR-DEMO001"),
        ("BOM-SUR", 8.75, 640, "CAR-DEMO002"),
        ("BLR-MYS", 7.20, 720, "CAR-DEMO003"),
        ("HYD-VIJ", 8.10, 830, "CAR-DEMO004"),
        ("PUN-NAG", 9.80, 910, "CAR-DEMO001"),
        ("CHN-CBE", 7.90, 1000, "CAR-DEMO002"),
        ("KOL-BBS", 8.60, 1120, "CAR-DEMO003"),
        ("AHM-RAJ", 6.90, 1250, "CAR-DEMO004"),
        ("LKO-KNP", 5.80, 1390, "CAR-DEMO001"),
        ("IND-BPL", 6.40, 1500, "CAR-DEMO002"),
    ]

    for idx, (lane, rate, weight, carrier_id) in enumerate(deterministic_lanes, start=1):
        contract_id = f"DEMO-CC-DET-{idx:03d}"
        shipment_id = f"DEMO-SHP-{idx:03d}"
        bol_id = f"DEMO-BOL-{idx:03d}"
        bill_id = f"DEMO-FB-{idx:03d}"
        fsc_percent = 7 + (idx % 3)
        base, fsc, gst, total = _bill_amounts(weight, rate, fsc_percent)
        carrier_name = next(c["name"] for c in carriers if c["id"] == carrier_id)

        contracts.append({
            "id": contract_id,
            "carrier_id": carrier_id,
            "effective_date": "2025-01-01",
            "expiry_date": "2025-12-31",
            "status": "active",
            "notes": "Demo deterministic single-contract lane",
            "rate_card": [{
                "lane": lane,
                "description": f"Demo deterministic lane {lane}",
                "rate_per_kg": rate,
                "min_charge": 1000.00,
                "fuel_surcharge_percent": fsc_percent,
            }],
        })
        shipments.append({
            "id": shipment_id,
            "carrier_id": carrier_id,
            "contract_id": contract_id,
            "lane": lane,
            "shipment_date": "2025-06-01",
            "status": "delivered",
            "total_weight_kg": weight,
            "notes": "Demo deterministic shipment",
        })
        bols.append({
            "id": bol_id,
            "shipment_id": shipment_id,
            "delivery_date": "2025-06-03",
            "actual_weight_kg": weight,
            "notes": "Demo deterministic BOL",
        })
        freight_bills.append({
            "id": bill_id,
            "carrier_id": carrier_id,
            "carrier_name": carrier_name,
            "bill_number": f"DEMO/DET/{idx:03d}",
            "bill_date": "2025-06-05",
            "shipment_reference": shipment_id,
            "lane": lane,
            "billed_weight_kg": weight,
            "rate_per_kg": rate,
            "billing_unit": "kg",
            "base_charge": base,
            "fuel_surcharge": fsc,
            "gst_amount": gst,
            "total_amount": total,
            "demo_kind": "deterministic",
        })

    llm_lanes = [
        ("DEL-AGR", 12.20, 1040, "CAR-DEMO001", "Atlas Freight Demo"),
        ("BOM-NAS", 11.40, 1180, "CAR-DEMO002", "Northline Demo Logistics"),
        ("BLR-HUB", 10.60, 1260, "CAR-DEMO003", "Meridian Demo Transport"),
        ("HYD-WGL", 9.90, 1340, "CAR-DEMO004", "Skyline Demo Cargo"),
        ("PUN-GOA", 13.10, 1420, "CAR-DEMO001", "Atlas Demo Freight Services"),
        ("CHN-MDU", 8.80, 1500, "CAR-DEMO002", "Northline Logistics Demo"),
        ("KOL-RNC", 12.70, 1660, "CAR-DEMO003", "Meridian Transport Demo"),
        ("AHM-UDA", 10.30, 1740, "CAR-DEMO004", "Skyline Cargo Demo"),
        ("LKO-VNS", 7.70, 1820, "CAR-DEMO001", "Demo Atlas Freight Co"),
        ("IND-UJN", 8.40, 1900, "CAR-DEMO002", "Demo Northline Freight"),
    ]

    for offset, (lane, premium_rate, weight, carrier_id, fuzzy_name) in enumerate(llm_lanes, start=1):
        idx = DEMO_DETERMINISTIC_COUNT + offset
        standard_contract_id = f"DEMO-CC-LLM-{offset:03d}-STD"
        premium_contract_id = f"DEMO-CC-LLM-{offset:03d}-PRM"
        shipment_id = f"DEMO-SHP-{idx:03d}"
        bol_id = f"DEMO-BOL-{idx:03d}"
        bill_id = f"DEMO-FB-{idx:03d}"
        fsc_percent = 8
        standard_rate = _money(premium_rate - 1.35)
        base, fsc, gst, total = _bill_amounts(weight, premium_rate, fsc_percent)

        contracts.extend([
            {
                "id": standard_contract_id,
                "carrier_id": carrier_id,
                "effective_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "status": "active",
                "notes": "Demo standard contract; intentionally overlaps premium contract",
                "rate_card": [{
                    "lane": lane,
                    "description": f"Demo standard overlapping lane {lane}",
                    "rate_per_kg": standard_rate,
                    "min_charge": 1200.00,
                    "fuel_surcharge_percent": fsc_percent,
                }],
            },
            {
                "id": premium_contract_id,
                "carrier_id": carrier_id,
                "effective_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "status": "active",
                "notes": "Demo premium express contract; bill rate is designed to match this contract",
                "rate_card": [{
                    "lane": lane,
                    "description": f"Demo premium overlapping lane {lane}",
                    "rate_per_kg": premium_rate,
                    "min_charge": 1200.00,
                    "min_weight_kg": 1000,
                    "fuel_surcharge_percent": fsc_percent,
                }],
            },
        ])
        shipments.append({
            "id": shipment_id,
            "carrier_id": carrier_id,
            "contract_id": premium_contract_id,
            "lane": lane,
            "shipment_date": "2025-07-01",
            "status": "delivered",
            "total_weight_kg": weight,
            "notes": "Demo LLM path shipment; bill omits carrier_id to trigger carrier normalization",
        })
        bols.append({
            "id": bol_id,
            "shipment_id": shipment_id,
            "delivery_date": "2025-07-04",
            "actual_weight_kg": weight,
            "notes": "Demo LLM path BOL",
        })
        freight_bills.append({
            "id": bill_id,
            "carrier_id": None,
            "carrier_name": fuzzy_name,
            "bill_number": f"DEMO/LLM/{offset:03d}",
            "bill_date": "2025-07-06",
            "shipment_reference": shipment_id,
            "lane": lane,
            "billed_weight_kg": weight,
            "rate_per_kg": premium_rate,
            "billing_unit": "kg",
            "base_charge": base,
            "fuel_surcharge": fsc,
            "gst_amount": gst,
            "total_amount": total,
            "demo_kind": "llm",
        })

    return {
        "carriers": carriers,
        "carrier_contracts": contracts,
        "shipments": shipments,
        "bills_of_lading": bols,
        "freight_bills": freight_bills,
    }


async def clear_demo_data(db: AsyncSession) -> dict[str, int]:
    """Remove only demo-prefixed records."""
    demo_bill_ids = select(FreightBill.id).where(FreightBill.id.like("DEMO-FB-%"))

    audit_result = await db.execute(
        delete(AuditLog)
        .where(AuditLog.freight_bill_id.in_(demo_bill_ids))
        .execution_options(synchronize_session=False)
    )
    bill_result = await db.execute(
        delete(FreightBill)
        .where(FreightBill.id.like("DEMO-FB-%"))
        .execution_options(synchronize_session=False)
    )
    bol_result = await db.execute(
        delete(BillOfLading)
        .where(BillOfLading.id.like("DEMO-BOL-%"))
        .execution_options(synchronize_session=False)
    )
    shipment_result = await db.execute(
        delete(Shipment)
        .where(Shipment.id.like("DEMO-SHP-%"))
        .execution_options(synchronize_session=False)
    )
    contract_result = await db.execute(
        delete(CarrierContract)
        .where(CarrierContract.id.like("DEMO-CC-%"))
        .execution_options(synchronize_session=False)
    )
    carrier_result = await db.execute(
        delete(Carrier)
        .where(Carrier.id.like("CAR-DEMO%"))
        .execution_options(synchronize_session=False)
    )

    await db.commit()
    return {
        "audit_logs": audit_result.rowcount or 0,
        "freight_bills": bill_result.rowcount or 0,
        "bills_of_lading": bol_result.rowcount or 0,
        "shipments": shipment_result.rowcount or 0,
        "carrier_contracts": contract_result.rowcount or 0,
        "carriers": carrier_result.rowcount or 0,
    }


async def load_demo_data(db: AsyncSession) -> dict:
    """Clear existing demo records, load fresh demo records, and return bill payloads."""
    removed = await clear_demo_data(db)
    data = build_demo_dataset()

    for row in data["carriers"]:
        db.add(Carrier(**row))
    await db.flush()

    for row in data["carrier_contracts"]:
        db.add(CarrierContract(**row))
    await db.flush()

    for row in data["shipments"]:
        db.add(Shipment(**row))
    await db.flush()

    for row in data["bills_of_lading"]:
        db.add(BillOfLading(**row))
    await db.flush()

    bill_payloads = []
    for row in data["freight_bills"]:
        demo_kind = row.pop("demo_kind")
        bill_payloads.append(dict(row))
        db.add(FreightBill(
            **row,
            status=FreightBillStatus.pending,
            evidence={"demo": True, "demo_kind": demo_kind},
        ))
        db.add(AuditLog(
            freight_bill_id=row["id"],
            event="demo_bill_loaded",
            detail={"source": "demo_data", "demo_kind": demo_kind},
        ))

    await db.commit()
    return {
        "removed": removed,
        "loaded": {
            "carriers": len(data["carriers"]),
            "carrier_contracts": len(data["carrier_contracts"]),
            "shipments": len(data["shipments"]),
            "bills_of_lading": len(data["bills_of_lading"]),
            "freight_bills": len(bill_payloads),
            "deterministic_bills": DEMO_DETERMINISTIC_COUNT,
            "llm_bills": DEMO_LLM_COUNT,
        },
        "bill_payloads": bill_payloads,
    }
