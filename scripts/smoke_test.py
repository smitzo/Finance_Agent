"""
Basic API smoke test for local/dev runs.

Usage:
  python scripts/smoke_test.py
  python scripts/smoke_test.py http://localhost:8000
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

import httpx


def _build_payload() -> dict[str, Any]:
    suffix = str(int(time.time()))
    return {
        "id": f"FB-SMOKE-{suffix}",
        "carrier_id": "CAR001",
        "carrier_name": "Safexpress Logistics",
        "bill_number": f"SMOKE/{suffix}",
        "bill_date": "2025-02-15",
        "shipment_reference": "SHP-2025-002",
        "lane": "DEL-BLR",
        "billed_weight_kg": 850,
        "rate_per_kg": 15.00,
        "base_charge": 12750.00,
        "fuel_surcharge": 1020.00,
        "gst_amount": 2479.00,
        "total_amount": 16249.00,
    }


async def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    payload = _build_payload()
    bill_id = payload["id"]

    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print(f"[ok] health: {health.json()}")

        ingest = await client.post("/freight-bills", json=payload)
        ingest.raise_for_status()
        print(f"[ok] ingest: {ingest.json()}")

        final_statuses = {"approved", "disputed", "rejected", "awaiting_review"}
        current = None
        for _ in range(30):
            await asyncio.sleep(1)
            resp = await client.get(f"/freight-bills/{bill_id}")
            resp.raise_for_status()
            current = resp.json()
            status = current.get("status")
            print(f"[poll] status={status} decision={current.get('decision')}")
            if status in final_statuses:
                break

        if not current:
            raise RuntimeError("No bill state returned while polling")

        if current.get("status") == "awaiting_review":
            review = await client.post(
                f"/review/{bill_id}",
                json={"reviewer_decision": "approve", "reviewer_notes": "Smoke test approval"},
            )
            review.raise_for_status()
            print(f"[ok] review submitted: {review.json()}")

            for _ in range(20):
                await asyncio.sleep(1)
                resp = await client.get(f"/freight-bills/{bill_id}")
                resp.raise_for_status()
                current = resp.json()
                print(f"[poll-resume] status={current.get('status')} decision={current.get('decision')}")
                if current.get("status") in {"approved", "disputed", "rejected"}:
                    break

        audit = await client.get(f"/freight-bills/{bill_id}/audit")
        audit.raise_for_status()
        print(f"[ok] audit entries: {len(audit.json())}")
        print(f"[done] final status={current.get('status')} decision={current.get('decision')}")


if __name__ == "__main__":
    asyncio.run(main())
