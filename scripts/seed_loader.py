"""
Seed Loader
===========
Loads logistics seed data into Postgres.
Run once after `docker-compose up`:

    python scripts/seed_loader.py

Safe to re-run — uses INSERT OR IGNORE semantics (skips existing rows).
"""

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

# Make sure app is importable from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.tenancy import normalize_tenant_id
from app.models.db_models import (
    AuditLog,
    Base,
    BillOfLading,
    Carrier,
    CarrierContract,
    FreightBill,
    FreightBillStatus,
    Shipment,
)

PROJECT_ROOT = Path(__file__).parent.parent
SEED_FILE_CANDIDATES = [
    PROJECT_ROOT / "seed_data.json",
]


def resolve_seed_path(arg_path: str | None = None) -> Path:
    if arg_path:
        candidate = Path(arg_path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if candidate.exists():
            return candidate

    for candidate in SEED_FILE_CANDIDATES:
        if candidate.exists():
            return candidate

    expected = ", ".join(str(p) for p in SEED_FILE_CANDIDATES)
    raise FileNotFoundError(f"No seed file found. Expected one of: {expected}")


async def _exists(db: AsyncSession, model, pk: str) -> bool:
    result = await db.get(model, pk)
    return result is not None


async def _find_existing_bill_by_business_key(
    db: AsyncSession,
    tenant_id: str,
    carrier_id: str | None,
    carrier_name: str | None,
    bill_number: str,
) -> FreightBill | None:
    if carrier_id:
        result = await db.execute(
            select(FreightBill).where(
                FreightBill.tenant_id == tenant_id,
                FreightBill.carrier_id == carrier_id,
                FreightBill.bill_number == bill_number,
            )
        )
        existing = result.scalars().first()
        if existing:
            return existing

    normalized_name = (carrier_name or "").strip().lower()
    if normalized_name:
        result = await db.execute(
            select(FreightBill).where(
                FreightBill.tenant_id == tenant_id,
                FreightBill.bill_number == bill_number,
            )
        )
        for row in result.scalars().all():
            if (row.carrier_name or "").strip().lower() == normalized_name:
                return row

    return None


async def load_seed(seed_path: Path | None = None, tenant_id: str | None = None) -> None:
    seed_path = seed_path or resolve_seed_path()
    tenant_id = normalize_tenant_id(tenant_id)
    print(f"Loading seed data from {seed_path} ...")
    print(f"Tenant: {tenant_id}")

    with open(seed_path) as f:
        data = json.load(f)

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Carriers
        for c in data.get("carriers", []):
            if not await _exists(db, Carrier, c["id"]):
                db.add(Carrier(
                    tenant_id=c.get("tenant_id", tenant_id),
                    id=c["id"],
                    name=c["name"],
                    carrier_code=c["carrier_code"],
                    gstin=c.get("gstin"),
                    bank_account=c.get("bank_account"),
                    status=c.get("status", "active"),
                    onboarded_on=c.get("onboarded_on"),
                ))
                print(f"  + Carrier {c['id']} ({c['name']})")
            else:
                print(f"  ~ Carrier {c['id']} already exists, skipping")

        await db.flush()

        # Contracts
        for cc in data.get("carrier_contracts", []):
            if not await _exists(db, CarrierContract, cc["id"]):
                db.add(CarrierContract(
                    tenant_id=cc.get("tenant_id", tenant_id),
                    id=cc["id"],
                    carrier_id=cc["carrier_id"],
                    effective_date=cc["effective_date"],
                    expiry_date=cc["expiry_date"],
                    status=cc.get("status", "active"),
                    notes=cc.get("notes"),
                    rate_card=cc["rate_card"],
                ))
                print(f"  + Contract {cc['id']}")
            else:
                print(f"  ~ Contract {cc['id']} already exists, skipping")

        await db.flush()

        # Shipments
        for s in data.get("shipments", []):
            if not await _exists(db, Shipment, s["id"]):
                db.add(Shipment(
                    tenant_id=s.get("tenant_id", tenant_id),
                    id=s["id"],
                    carrier_id=s["carrier_id"],
                    contract_id=s.get("contract_id"),
                    lane=s["lane"],
                    shipment_date=s.get("shipment_date"),
                    status=s.get("status"),
                    total_weight_kg=s.get("total_weight_kg"),
                    notes=s.get("notes"),
                ))
                print(f"  + Shipment {s['id']}")
            else:
                print(f"  ~ Shipment {s['id']} already exists, skipping")

        await db.flush()

        # Bills of Lading
        for b in data.get("bills_of_lading", []):
            if not await _exists(db, BillOfLading, b["id"]):
                db.add(BillOfLading(
                    tenant_id=b.get("tenant_id", tenant_id),
                    id=b["id"],
                    shipment_id=b["shipment_id"],
                    delivery_date=b.get("delivery_date"),
                    actual_weight_kg=b.get("actual_weight_kg"),
                    notes=b.get("notes") or b.get("_note"),
                ))
                print(f"  + BOL {b['id']}")
            else:
                print(f"  ~ BOL {b['id']} already exists, skipping")

        await db.flush()

        # Freight Bills
        for fb in data.get("freight_bills", []):
            if await _exists(db, FreightBill, fb["id"]):
                print(f"  ~ FreightBill {fb['id']} already exists, skipping")
                continue

            duplicate = await _find_existing_bill_by_business_key(
                db,
                tenant_id=fb.get("tenant_id", tenant_id),
                carrier_id=fb.get("carrier_id"),
                carrier_name=fb.get("carrier_name"),
                bill_number=fb["bill_number"],
            )
            if duplicate:
                print(
                    "  ~ FreightBill "
                    f"{fb['id']} skipped because bill_number '{fb['bill_number']}' "
                    f"already exists for the same carrier (existing id={duplicate.id})"
                )
                continue

            evidence = {}
            if fb.get("_scenario"):
                evidence["seed_scenario"] = fb["_scenario"]

            db.add(FreightBill(
                tenant_id=fb.get("tenant_id", tenant_id),
                id=fb["id"],
                carrier_id=fb.get("carrier_id"),
                carrier_name=fb["carrier_name"],
                bill_number=fb["bill_number"],
                bill_date=fb.get("bill_date"),
                shipment_reference=fb.get("shipment_reference"),
                lane=fb.get("lane"),
                billed_weight_kg=fb.get("billed_weight_kg"),
                rate_per_kg=fb.get("rate_per_kg"),
                billing_unit=fb.get("billing_unit", "kg"),
                base_charge=fb.get("base_charge"),
                fuel_surcharge=fb.get("fuel_surcharge"),
                gst_amount=fb.get("gst_amount"),
                total_amount=fb.get("total_amount"),
                status=FreightBillStatus.pending,
                evidence=evidence or None,
            ))
            db.add(AuditLog(
                tenant_id=fb.get("tenant_id", tenant_id),
                freight_bill_id=fb["id"],
                event="seed_bill_loaded",
                detail={"source": "seed_loader"},
            ))
            print(f"  + FreightBill {fb['id']}")

        await db.commit()

    print("\nSeed data loaded successfully.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    cli_path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(load_seed(resolve_seed_path(cli_path)))
