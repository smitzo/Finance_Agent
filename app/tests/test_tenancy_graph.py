from __future__ import annotations

import pytest

from app.services.demo_data_service import build_demo_dataset
from app.services.graph_service import MemoryGraphBackend
from app.tenancy import normalize_tenant_id


def test_normalize_tenant_id_defaults_and_validates() -> None:
    assert normalize_tenant_id(None) == "default"
    assert normalize_tenant_id("acme_ops-1") == "acme_ops-1"

    with pytest.raises(ValueError):
        normalize_tenant_id("../bad")


def test_demo_dataset_assigns_every_record_to_tenant() -> None:
    tenant_id = "tenant_a"
    data = build_demo_dataset(tenant_id)

    for rows in data.values():
        assert rows
        assert {row["tenant_id"] for row in rows} == {tenant_id}


@pytest.mark.asyncio
async def test_memory_graph_duplicate_lookup_is_tenant_scoped() -> None:
    graph = MemoryGraphBackend()
    await graph.add_freight_bill("tenant_a", "FB-1", {
        "id": "FB-1",
        "bill_number": "INV-100",
        "carrier_id": "CAR-1",
        "carrier_name": "Carrier One",
    })
    await graph.add_freight_bill("tenant_b", "FB-2", {
        "id": "FB-2",
        "bill_number": "INV-100",
        "carrier_id": "CAR-1",
        "carrier_name": "Carrier One",
    })

    tenant_a_dupes = await graph.find_duplicate_bill_ids(
        "tenant_a",
        bill_number="INV-100",
        carrier_id="CAR-1",
        carrier_name=None,
        exclude_bill_id="FB-NEW",
    )
    tenant_b_dupes = await graph.find_duplicate_bill_ids(
        "tenant_b",
        bill_number="INV-100",
        carrier_id="CAR-1",
        carrier_name=None,
        exclude_bill_id="FB-NEW",
    )

    assert tenant_a_dupes == ["FB-1"]
    assert tenant_b_dupes == ["FB-2"]
