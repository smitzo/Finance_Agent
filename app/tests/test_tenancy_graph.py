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


@pytest.mark.asyncio
async def test_memory_graph_detects_bill_anomalies() -> None:
    graph = MemoryGraphBackend()
    tenant_id = "tenant_a"
    graph._add_node(tenant_id, "carrier:CAR-1", {
        "id": "CAR-1",
        "type": "carrier",
        "tenant_id": tenant_id,
        "name": "Carrier One",
    })
    graph._add_node(tenant_id, "contract:CC-1", {
        "id": "CC-1",
        "type": "contract",
        "tenant_id": tenant_id,
        "carrier_id": "CAR-1",
    })
    graph._add_node(tenant_id, "lane:DEL-BLR", {"type": "lane", "tenant_id": tenant_id, "lane": "DEL-BLR"})
    graph._add_edge(tenant_id, "carrier:CAR-1", "contract:CC-1", {"rel": "has_contract"})
    graph._add_edge(
        tenant_id,
        "contract:CC-1",
        "lane:DEL-BLR",
        {"rel": "covers_lane", "rate_row": {"lane": "DEL-BLR", "rate_per_kg": 10.0}},
    )
    graph._add_node(tenant_id, "shipment:SHP-1", {"id": "SHP-1", "type": "shipment", "tenant_id": tenant_id})
    graph._add_node(tenant_id, "bol:BOL-1", {
        "id": "BOL-1",
        "type": "bol",
        "tenant_id": tenant_id,
        "actual_weight_kg": 100,
    })
    graph._add_edge(tenant_id, "shipment:SHP-1", "bol:BOL-1", {"rel": "has_bol"})
    await graph.add_freight_bill(tenant_id, "FB-1", {
        "id": "FB-1",
        "bill_number": "INV-100",
        "carrier_id": "CAR-1",
        "carrier_name": "Carrier One",
        "shipment_reference": "SHP-1",
        "lane": "DEL-BLR",
        "billed_weight_kg": 140,
        "rate_per_kg": 15.0,
    })
    await graph.add_freight_bill(tenant_id, "FB-2", {
        "id": "FB-2",
        "bill_number": "INV-100",
        "carrier_id": "CAR-1",
        "carrier_name": "Carrier One",
        "shipment_reference": "SHP-1",
        "lane": "DEL-BLR",
        "billed_weight_kg": 90,
        "rate_per_kg": 10.0,
    })

    anomalies = await graph.detect_anomalies_for_bill(tenant_id, "FB-1")
    codes = {anomaly["code"] for anomaly in anomalies}

    assert {"GRAPH_DUPLICATE_BILL", "GRAPH_WEIGHT_OVER_BOL", "GRAPH_RATE_OUTLIER"} <= codes
