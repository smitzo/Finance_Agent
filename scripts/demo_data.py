"""
Convenience client for demo data admin endpoints.

Usage:
  python scripts/demo_data.py load
  python scripts/demo_data.py clear
  python scripts/demo_data.py load http://127.0.0.1:8000
"""

from __future__ import annotations

import asyncio
import json
import sys

import httpx


async def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "load"
    base_url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        if action in {"load", "process"}:
            response = await client.post("/admin/demo/load")
        elif action in {"clear", "remove", "delete"}:
            response = await client.delete("/admin/demo")
        else:
            raise SystemExit("Usage: python scripts/demo_data.py [load|clear] [base_url]")

        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
