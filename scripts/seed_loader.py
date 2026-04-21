"""
Seed Loader
===========
Loads seed_data_logistics.json into Postgres.
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

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.models.db_models import Base, Carrier, CarrierContract, Shipment, BillOfLading

SEED_FILE = Path(__file__).parent.parent / "seed_data_logistics.json"


async def _exists(db: AsyncSession, model, pk: str) -> bool:
    result = await db.get(model, pk)
    return result is not None


async def load_seed(seed_path: Path = SEED_FILE) -> None:
    print(f"Loading seed data from {seed_path} ...")

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
                    id=b["id"],
                    shipment_id=b["shipment_id"],
                    delivery_date=b.get("delivery_date"),
                    actual_weight_kg=b.get("actual_weight_kg"),
                    notes=b.get("notes") or b.get("_note"),
                ))
                print(f"  + BOL {b['id']}")
            else:
                print(f"  ~ BOL {b['id']} already exists, skipping")

        await db.commit()

    print("\nSeed data loaded successfully.")


if __name__ == "__main__":
    asyncio.run(load_seed())