"""
Graph Service
=============
Tenant-aware graph facade used by the agent.

The relational database remains the source of truth. A graph backend is built
from those rows and then queried for traversal-heavy context such as carrier ->
contracts -> lanes -> shipments -> BOLs -> freight bills.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import Carrier, CarrierContract, Shipment, BillOfLading, FreightBill
from app.tenancy import normalize_tenant_id


class GraphBackend(Protocol):
    async def build(self, db: AsyncSession, tenant_id: str) -> None: ...
    async def add_freight_bill(self, tenant_id: str, fb_id: str, fb_data: dict) -> None: ...
    async def list_carriers(self, tenant_id: str) -> list[dict]: ...
    async def get_carrier_node(self, tenant_id: str, carrier_id: str) -> dict | None: ...
    async def get_contracts_for_lane(self, tenant_id: str, carrier_id: str, lane: str) -> list[dict]: ...
    async def get_shipment_node(self, tenant_id: str, shipment_id: str) -> dict | None: ...
    async def get_bols_for_shipment(self, tenant_id: str, shipment_id: str) -> list[dict]: ...
    async def get_freight_bill_node(self, tenant_id: str, fb_id: str) -> dict | None: ...
    async def get_freight_bills_for_shipment(self, tenant_id: str, shipment_id: str) -> list[str]: ...
    async def find_duplicate_bill_ids(
        self,
        tenant_id: str,
        bill_number: str,
        carrier_id: str | None,
        carrier_name: str | None,
        exclude_bill_id: str,
    ) -> list[str]: ...


class MemoryGraphBackend:
    """In-process graph backend for tests and local fallback."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, dict]] = defaultdict(dict)
        self._out_edges: dict[str, dict[str, list[tuple[str, dict]]]] = defaultdict(lambda: defaultdict(list))
        self._in_edges: dict[str, dict[str, list[tuple[str, dict]]]] = defaultdict(lambda: defaultdict(list))

    def _add_node(self, tenant_id: str, node_id: str, data: dict) -> None:
        self._nodes[tenant_id][node_id] = data

    def _add_edge(self, tenant_id: str, source: str, target: str, data: dict) -> None:
        self._out_edges[tenant_id][source].append((target, data))
        self._in_edges[tenant_id][target].append((source, data))

    async def build(self, db: AsyncSession, tenant_id: str) -> None:
        tenant_id = normalize_tenant_id(tenant_id)
        self._nodes[tenant_id] = {}
        self._out_edges[tenant_id] = defaultdict(list)
        self._in_edges[tenant_id] = defaultdict(list)

        carriers = (
            await db.execute(select(Carrier).where(Carrier.tenant_id == tenant_id))
        ).scalars().all()
        for c in carriers:
            self._add_node(tenant_id, f"carrier:{c.id}", {
                "id": c.id,
                "type": "carrier",
                "tenant_id": tenant_id,
                "name": c.name,
                "code": c.carrier_code,
                "status": c.status,
            })

        contracts = (
            await db.execute(select(CarrierContract).where(CarrierContract.tenant_id == tenant_id))
        ).scalars().all()
        for cc in contracts:
            node_id = f"contract:{cc.id}"
            self._add_node(tenant_id, node_id, {
                "id": cc.id,
                "type": "contract",
                "tenant_id": tenant_id,
                "carrier_id": cc.carrier_id,
                "effective_date": cc.effective_date,
                "expiry_date": cc.expiry_date,
                "status": cc.status,
                "rate_card": cc.rate_card,
                "notes": cc.notes,
            })
            self._add_edge(tenant_id, f"carrier:{cc.carrier_id}", node_id, {"rel": "has_contract"})

            for rate_row in cc.rate_card:
                lane = rate_row.get("lane")
                if lane:
                    lane_node = f"lane:{lane}"
                    if lane_node not in self._nodes[tenant_id]:
                        self._add_node(tenant_id, lane_node, {"type": "lane", "tenant_id": tenant_id, "lane": lane})
                    self._add_edge(tenant_id, node_id, lane_node, {"rel": "covers_lane", "rate_row": rate_row})

        shipments = (
            await db.execute(select(Shipment).where(Shipment.tenant_id == tenant_id))
        ).scalars().all()
        for s in shipments:
            node_id = f"shipment:{s.id}"
            self._add_node(tenant_id, node_id, {
                "id": s.id,
                "type": "shipment",
                "tenant_id": tenant_id,
                "carrier_id": s.carrier_id,
                "contract_id": s.contract_id,
                "lane": s.lane,
                "shipment_date": s.shipment_date,
                "status": s.status,
                "total_weight_kg": s.total_weight_kg,
            })
            self._add_edge(tenant_id, f"carrier:{s.carrier_id}", node_id, {"rel": "has_shipment"})
            if s.contract_id:
                self._add_edge(tenant_id, f"contract:{s.contract_id}", node_id, {"rel": "has_shipment"})

        bols = (
            await db.execute(select(BillOfLading).where(BillOfLading.tenant_id == tenant_id))
        ).scalars().all()
        for b in bols:
            node_id = f"bol:{b.id}"
            self._add_node(tenant_id, node_id, {
                "id": b.id,
                "type": "bol",
                "tenant_id": tenant_id,
                "shipment_id": b.shipment_id,
                "delivery_date": b.delivery_date,
                "actual_weight_kg": b.actual_weight_kg,
            })
            self._add_edge(tenant_id, f"shipment:{b.shipment_id}", node_id, {"rel": "has_bol"})

        freight_bills = (
            await db.execute(select(FreightBill).where(FreightBill.tenant_id == tenant_id))
        ).scalars().all()
        for fb in freight_bills:
            await self.add_freight_bill(tenant_id, fb.id, {
                "id": fb.id,
                "tenant_id": tenant_id,
                "carrier_id": fb.carrier_id,
                "carrier_name": fb.carrier_name,
                "bill_number": fb.bill_number,
                "shipment_reference": fb.shipment_reference,
                "billed_weight_kg": fb.billed_weight_kg,
            })

    async def add_freight_bill(self, tenant_id: str, fb_id: str, fb_data: dict) -> None:
        tenant_id = normalize_tenant_id(tenant_id)
        node_id = f"fb:{fb_id}"
        self._add_node(tenant_id, node_id, {"type": "freight_bill", "tenant_id": tenant_id, **fb_data})
        if fb_data.get("shipment_reference"):
            shp_node = f"shipment:{fb_data['shipment_reference']}"
            if shp_node in self._nodes[tenant_id]:
                self._add_edge(tenant_id, node_id, shp_node, {"rel": "references"})

    async def list_carriers(self, tenant_id: str) -> list[dict]:
        tenant_id = normalize_tenant_id(tenant_id)
        return [
            {"id": node_id.replace("carrier:", ""), "name": data.get("name", "")}
            for node_id, data in self._nodes[tenant_id].items()
            if data.get("type") == "carrier"
        ]

    async def get_carrier_node(self, tenant_id: str, carrier_id: str) -> dict | None:
        return self._nodes[normalize_tenant_id(tenant_id)].get(f"carrier:{carrier_id}")

    async def get_contracts_for_lane(self, tenant_id: str, carrier_id: str, lane: str) -> list[dict]:
        tenant_id = normalize_tenant_id(tenant_id)
        results = []
        for contract_node, data in self._out_edges[tenant_id].get(f"carrier:{carrier_id}", []):
            if data.get("rel") != "has_contract":
                continue
            for lane_node, edge_data in self._out_edges[tenant_id].get(contract_node, []):
                if edge_data.get("rel") == "covers_lane" and self._nodes[tenant_id][lane_node].get("lane") == lane:
                    contract_data = dict(self._nodes[tenant_id][contract_node])
                    contract_data["matched_rate_row"] = edge_data.get("rate_row")
                    results.append(contract_data)
        return results

    async def get_shipment_node(self, tenant_id: str, shipment_id: str) -> dict | None:
        return self._nodes[normalize_tenant_id(tenant_id)].get(f"shipment:{shipment_id}")

    async def get_bols_for_shipment(self, tenant_id: str, shipment_id: str) -> list[dict]:
        tenant_id = normalize_tenant_id(tenant_id)
        return [
            dict(self._nodes[tenant_id][bol_node])
            for bol_node, data in self._out_edges[tenant_id].get(f"shipment:{shipment_id}", [])
            if data.get("rel") == "has_bol"
        ]

    async def get_freight_bill_node(self, tenant_id: str, fb_id: str) -> dict | None:
        return self._nodes[normalize_tenant_id(tenant_id)].get(f"fb:{fb_id}")

    async def get_freight_bills_for_shipment(self, tenant_id: str, shipment_id: str) -> list[str]:
        tenant_id = normalize_tenant_id(tenant_id)
        fb_ids = []
        for source, data in self._in_edges[tenant_id].get(f"shipment:{shipment_id}", []):
            node = self._nodes[tenant_id].get(source, {})
            if data.get("rel") == "references" and node.get("type") == "freight_bill":
                fb_ids.append(node.get("id", source.replace("fb:", "")))
        return fb_ids

    async def find_duplicate_bill_ids(
        self,
        tenant_id: str,
        bill_number: str,
        carrier_id: str | None,
        carrier_name: str | None,
        exclude_bill_id: str,
    ) -> list[str]:
        tenant_id = normalize_tenant_id(tenant_id)
        incoming_carrier_name = (carrier_name or "").strip().lower()
        duplicates = []
        for node_id, data in self._nodes[tenant_id].items():
            if data.get("type") != "freight_bill" or data.get("id") == exclude_bill_id:
                continue
            if data.get("bill_number") != bill_number:
                continue
            node_carrier_id = data.get("carrier_id")
            node_carrier_name = (data.get("carrier_name") or "").strip().lower()
            same_carrier = False
            if carrier_id and node_carrier_id:
                same_carrier = carrier_id == node_carrier_id
            elif incoming_carrier_name and node_carrier_name:
                same_carrier = incoming_carrier_name == node_carrier_name
            else:
                same_carrier = not carrier_id and not incoming_carrier_name
            if same_carrier:
                duplicates.append(data.get("id", node_id.replace("fb:", "")))
        return duplicates


class GraphService:
    def __init__(self, backend: GraphBackend | None = None) -> None:
        self.backend = backend or MemoryGraphBackend()

    async def build(self, db: AsyncSession, tenant_id: str = "default") -> None:
        await self.backend.build(db, normalize_tenant_id(tenant_id))

    async def add_freight_bill(self, tenant_id: str, fb_id: str, fb_data: dict) -> None:
        await self.backend.add_freight_bill(normalize_tenant_id(tenant_id), fb_id, fb_data)

    async def list_carriers(self, tenant_id: str) -> list[dict]:
        return await self.backend.list_carriers(normalize_tenant_id(tenant_id))

    async def get_carrier_node(self, tenant_id: str, carrier_id: str) -> dict | None:
        return await self.backend.get_carrier_node(normalize_tenant_id(tenant_id), carrier_id)

    async def get_contracts_for_lane(self, tenant_id: str, carrier_id: str, lane: str) -> list[dict]:
        return await self.backend.get_contracts_for_lane(normalize_tenant_id(tenant_id), carrier_id, lane)

    async def get_shipment_node(self, tenant_id: str, shipment_id: str) -> dict | None:
        return await self.backend.get_shipment_node(normalize_tenant_id(tenant_id), shipment_id)

    async def get_bols_for_shipment(self, tenant_id: str, shipment_id: str) -> list[dict]:
        return await self.backend.get_bols_for_shipment(normalize_tenant_id(tenant_id), shipment_id)

    async def get_freight_bill_node(self, tenant_id: str, fb_id: str) -> dict | None:
        return await self.backend.get_freight_bill_node(normalize_tenant_id(tenant_id), fb_id)

    async def get_freight_bills_for_shipment(self, tenant_id: str, shipment_id: str) -> list[str]:
        return await self.backend.get_freight_bills_for_shipment(normalize_tenant_id(tenant_id), shipment_id)

    async def find_duplicate_bill_ids(
        self,
        tenant_id: str,
        bill_number: str,
        carrier_id: str | None,
        carrier_name: str | None,
        exclude_bill_id: str,
    ) -> list[str]:
        return await self.backend.find_duplicate_bill_ids(
            normalize_tenant_id(tenant_id),
            bill_number,
            carrier_id,
            carrier_name,
            exclude_bill_id,
        )


_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
    return _graph_service
