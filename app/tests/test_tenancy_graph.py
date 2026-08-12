from __future__ import annotations

import pytest

from app.services.demo_data_service import build_demo_dataset
from app.services.graph_service import GraphService, MemoryGraphBackend, Neo4jGraphBackend
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


def test_neo4j_contract_props_serializes_nested_rate_card() -> None:
    row = {
        "id": "CC-1",
        "rate_card": [{"lane": "DEL-BLR", "rate_per_kg": 12.5}],
    }

    props = Neo4jGraphBackend._contract_props(row)

    assert "rate_card" not in props
    assert props["rate_card_json"] == '[{"lane": "DEL-BLR", "rate_per_kg": 12.5}]'


@pytest.mark.asyncio
async def test_shared_graph_is_not_rebuilt_by_each_worker_process() -> None:
    class SharedBackend:
        process_local = False

        def __init__(self) -> None:
            self.build_calls = 0

        async def build(self, _db, _tenant_id: str) -> None:
            self.build_calls += 1

    backend = SharedBackend()
    graph = GraphService(backend=backend)

    await graph.ensure_built(None, "tenant_a")
    await graph.ensure_built(None, "tenant_a")

    assert backend.build_calls == 0


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


@pytest.mark.asyncio
async def test_overlapping_premium_contract_is_not_a_graph_rate_outlier() -> None:
    graph = MemoryGraphBackend()
    tenant_id = "tenant_a"
    graph._add_node(tenant_id, "carrier:CAR-1", {
        "id": "CAR-1",
        "type": "carrier",
        "tenant_id": tenant_id,
        "name": "Carrier One",
    })
    graph._add_node(tenant_id, "lane:DEL-BLR", {
        "type": "lane",
        "tenant_id": tenant_id,
        "lane": "DEL-BLR",
    })
    for contract_id, rate in (("CC-STANDARD", 8.0), ("CC-PREMIUM", 10.0)):
        graph._add_node(tenant_id, f"contract:{contract_id}", {
            "id": contract_id,
            "type": "contract",
            "tenant_id": tenant_id,
            "carrier_id": "CAR-1",
        })
        graph._add_edge(
            tenant_id,
            "carrier:CAR-1",
            f"contract:{contract_id}",
            {"rel": "has_contract"},
        )
        graph._add_edge(
            tenant_id,
            f"contract:{contract_id}",
            "lane:DEL-BLR",
            {"rel": "covers_lane", "rate_row": {"lane": "DEL-BLR", "rate_per_kg": rate}},
        )

    await graph.add_freight_bill(tenant_id, "FB-PREMIUM", {
        "id": "FB-PREMIUM",
        "bill_number": "INV-PREMIUM",
        "carrier_id": "CAR-1",
        "carrier_name": "Carrier One",
        "shipment_reference": None,
        "lane": "DEL-BLR",
        "billed_weight_kg": 100,
        "rate_per_kg": 10.0,
    })

    anomalies = await graph.detect_anomalies_for_bill(tenant_id, "FB-PREMIUM")
    assert "GRAPH_RATE_OUTLIER" not in {anomaly["code"] for anomaly in anomalies}
