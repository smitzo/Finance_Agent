"""Real PostgreSQL integration coverage.

Run after migrations with:
TEST_DATABASE_URL=postgresql+asyncpg://... pytest -m integration
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from langgraph.graph import END, StateGraph
from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.checkpoint import checkpoint_database_url
from app.models.db_models import AuditLog, FreightBill
from app.services.freight_service import create_bill, find_by_idempotency_key, persist_result


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"),
]


@pytest_asyncio.fixture
async def db_session():
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    tenant_id = f"integration-{uuid.uuid4().hex[:10]}"
    async with session_factory() as session:
        yield session, tenant_id
        await session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
        await session.execute(delete(FreightBill).where(FreightBill.tenant_id == tenant_id))
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_migrated_schema_contains_worker_observability_columns(db_session) -> None:
    session, _tenant_id = db_session

    def column_names(sync_session) -> set[str]:
        return {column["name"] for column in inspect(sync_session.bind).get_columns("freight_bills")}

    columns = await session.run_sync(column_names)
    assert {"correlation_id", "celery_task_id", "processing_started_at", "processing_completed_at"} <= columns


@pytest.mark.asyncio
async def test_freight_service_round_trip_on_postgres(db_session) -> None:
    session, tenant_id = db_session
    bill_id = f"IT-FB-{uuid.uuid4().hex[:8]}"
    bill = {
        "id": bill_id,
        "tenant_id": tenant_id,
        "workflow_type": "freight_audit",
        "idempotency_key": f"idem-{bill_id}",
        "carrier_id": "IT-CARRIER",
        "carrier_name": "Integration Carrier",
        "bill_number": f"INV-{bill_id}",
        "bill_date": "2026-08-07",
        "shipment_reference": "IT-SHIPMENT",
        "lane": "DEL-BLR",
        "billed_weight_kg": 100.0,
        "rate_per_kg": 10.0,
        "billing_unit": "kg",
        "base_charge": 1000.0,
        "fuel_surcharge": 80.0,
        "gst_amount": 194.4,
        "total_amount": 1274.4,
    }

    await create_bill(session, bill, tenant_id)
    await session.commit()
    found = await find_by_idempotency_key(session, tenant_id, "freight_audit", bill["idempotency_key"])
    assert found is not None and found.id == bill_id

    await persist_result(
        session,
        bill_id,
        {
            "tenant_id": tenant_id,
            "findings": [{"code": "TOTAL_OK", "severity": "ok"}],
            "decision": "auto_approve",
            "confidence": 0.99,
            "explanation": "Integration path approved.",
            "audit": [{"event": "integration_completed"}],
        },
        interrupted=False,
        tenant_id=tenant_id,
    )

    row = (await session.execute(select(FreightBill).where(FreightBill.id == bill_id))).scalar_one()
    assert row.status.value == "approved"
    assert row.processing_completed_at is not None
    assert row.evidence["findings"][0]["code"] == "TOTAL_OK"


@pytest.mark.asyncio
async def test_async_postgres_saver_persists_graph_state() -> None:
    assert TEST_DATABASE_URL
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(checkpoint_database_url(TEST_DATABASE_URL)) as saver:
        await saver.setup()
        builder = StateGraph(dict)
        builder.add_node("increment", lambda state: {"value": state["value"] + 1})
        builder.set_entry_point("increment")
        builder.add_edge("increment", END)
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": f"integration-{uuid.uuid4().hex}"}}

        assert await graph.ainvoke({"value": 1}, config=config) == {"value": 2}
        snapshot = await graph.aget_state(config)
        assert snapshot.values["value"] == 2
