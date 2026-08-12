"""Initialize LangGraph's PostgreSQL-owned checkpoint schema once per release."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.checkpoint import setup_checkpoint_schema


if __name__ == "__main__":
    asyncio.run(setup_checkpoint_schema())
