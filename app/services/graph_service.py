"""
Graph Service
=============
Tenant-aware graph facade used by the agent.

The relational database remains the source of truth. A graph backend is built
from those rows and then queried for traversal-heavy context such as carrier ->
contracts -> lanes -> shipments -> BOLs -> freight bills.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db_models import Carrier, CarrierContract, Shipment, BillOfLading, FreightBill
from app.tenancy import normalize_tenant_id

logger = logging.getLogger(__name__)
settings = get_settings()


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
    async def health(self) -> dict: ...
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

    async def health(self) -> dict:
        return {"backend": "memory", "status": "ok", "tenants_loaded": len(self._nodes)}


class Neo4jGraphBackend:
    """Neo4j-backed graph traversal store for production workloads."""

    def __init__(self) -> None:
        from neo4j import AsyncGraphDatabase

        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=settings.neo4j_max_connection_pool_size,
        )
        self._database = settings.neo4j_database
        self._schema_ready = False

    async def close(self) -> None:
        await self._driver.close()

    async def health(self) -> dict:
        await self._driver.verify_connectivity()
        return {"backend": "neo4j", "status": "ok", "database": self._database}

    async def _execute(self, query: str, **params):
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, **params)
            return await result.data()

    async def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        statements = [
            "CREATE CONSTRAINT tenant_carrier_id IF NOT EXISTS FOR (n:Carrier) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE CONSTRAINT tenant_contract_id IF NOT EXISTS FOR (n:Contract) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE CONSTRAINT tenant_lane_id IF NOT EXISTS FOR (n:Lane) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE CONSTRAINT tenant_shipment_id IF NOT EXISTS FOR (n:Shipment) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE CONSTRAINT tenant_bol_id IF NOT EXISTS FOR (n:BOL) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE CONSTRAINT tenant_freight_bill_id IF NOT EXISTS FOR (n:FreightBill) REQUIRE (n.tenant_id, n.id) IS UNIQUE",
            "CREATE INDEX freight_bill_duplicate_lookup IF NOT EXISTS FOR (n:FreightBill) ON (n.tenant_id, n.bill_number, n.carrier_id)",
            "CREATE INDEX shipment_tenant_lookup IF NOT EXISTS FOR (n:Shipment) ON (n.tenant_id, n.id)",
            "CREATE INDEX lane_tenant_lookup IF NOT EXISTS FOR (n:Lane) ON (n.tenant_id, n.lane)",
        ]
        async with self._driver.session(database=self._database) as session:
            for statement in statements:
                await session.run(statement)
        self._schema_ready = True

    async def build(self, db: AsyncSession, tenant_id: str) -> None:
        tenant_id = normalize_tenant_id(tenant_id)
        await self._ensure_schema()

        carriers = (
            await db.execute(select(Carrier).where(Carrier.tenant_id == tenant_id))
        ).scalars().all()
        contracts = (
            await db.execute(select(CarrierContract).where(CarrierContract.tenant_id == tenant_id))
        ).scalars().all()
        shipments = (
            await db.execute(select(Shipment).where(Shipment.tenant_id == tenant_id))
        ).scalars().all()
        bols = (
            await db.execute(select(BillOfLading).where(BillOfLading.tenant_id == tenant_id))
        ).scalars().all()
        freight_bills = (
            await db.execute(select(FreightBill).where(FreightBill.tenant_id == tenant_id))
        ).scalars().all()

        async with self._driver.session(database=self._database) as session:
            await session.run("MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n", tenant_id=tenant_id)

            await session.run(
                """
                UNWIND $rows AS row
                MERGE (c:Carrier {tenant_id: row.tenant_id, id: row.id})
                SET c += row
                """,
                rows=[{
                    "tenant_id": tenant_id,
                    "id": c.id,
                    "type": "carrier",
                    "name": c.name,
                    "code": c.carrier_code,
                    "status": c.status,
                } for c in carriers],
            )

            contract_rows = []
            lane_rows = []
            for cc in contracts:
                contract_rows.append({
                    "tenant_id": tenant_id,
                    "id": cc.id,
                    "type": "contract",
                    "carrier_id": cc.carrier_id,
                    "effective_date": cc.effective_date,
                    "expiry_date": cc.expiry_date,
                    "status": cc.status,
                    "rate_card": cc.rate_card,
                    "notes": cc.notes,
                })
                for rate_row in cc.rate_card:
                    lane = rate_row.get("lane")
                    if lane:
                        lane_rows.append({
                            "tenant_id": tenant_id,
                            "contract_id": cc.id,
                            "lane_id": lane,
                            "lane": lane,
                            "rate_row": rate_row,
                        })

            await session.run(
                """
                UNWIND $rows AS row
                MERGE (cc:Contract {tenant_id: row.tenant_id, id: row.id})
                SET cc += row
                WITH cc, row
                MATCH (c:Carrier {tenant_id: row.tenant_id, id: row.carrier_id})
                MERGE (c)-[:HAS_CONTRACT]->(cc)
                """,
                rows=contract_rows,
            )
            await session.run(
                """
                UNWIND $rows AS row
                MERGE (l:Lane {tenant_id: row.tenant_id, id: row.lane_id})
                SET l.tenant_id = row.tenant_id, l.lane = row.lane, l.type = 'lane'
                WITH l, row
                MATCH (cc:Contract {tenant_id: row.tenant_id, id: row.contract_id})
                MERGE (cc)-[r:COVERS_LANE]->(l)
                SET r.rate_row = row.rate_row
                """,
                rows=lane_rows,
            )

            await session.run(
                """
                UNWIND $rows AS row
                MERGE (s:Shipment {tenant_id: row.tenant_id, id: row.id})
                SET s += row
                WITH s, row
                MATCH (c:Carrier {tenant_id: row.tenant_id, id: row.carrier_id})
                MERGE (c)-[:HAS_SHIPMENT]->(s)
                WITH s, row
                OPTIONAL MATCH (cc:Contract {tenant_id: row.tenant_id, id: row.contract_id})
                FOREACH (_ IN CASE WHEN cc IS NULL THEN [] ELSE [1] END |
                    MERGE (cc)-[:HAS_SHIPMENT]->(s)
                )
                """,
                rows=[{
                    "tenant_id": tenant_id,
                    "id": s.id,
                    "type": "shipment",
                    "carrier_id": s.carrier_id,
                    "contract_id": s.contract_id,
                    "lane": s.lane,
                    "shipment_date": s.shipment_date,
                    "status": s.status,
                    "total_weight_kg": s.total_weight_kg,
                } for s in shipments],
            )

            await session.run(
                """
                UNWIND $rows AS row
                MERGE (b:BOL {tenant_id: row.tenant_id, id: row.id})
                SET b += row
                WITH b, row
                MATCH (s:Shipment {tenant_id: row.tenant_id, id: row.shipment_id})
                MERGE (s)-[:HAS_BOL]->(b)
                """,
                rows=[{
                    "tenant_id": tenant_id,
                    "id": b.id,
                    "type": "bol",
                    "shipment_id": b.shipment_id,
                    "delivery_date": b.delivery_date,
                    "actual_weight_kg": b.actual_weight_kg,
                } for b in bols],
            )

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
        await self._ensure_schema()
        await self._execute(
            """
            MERGE (fb:FreightBill {tenant_id: $tenant_id, id: $fb_id})
            SET fb += $props, fb.type = 'freight_bill'
            WITH fb
            OPTIONAL MATCH (s:Shipment {tenant_id: $tenant_id, id: $shipment_reference})
            FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END |
                MERGE (fb)-[:REFERENCES]->(s)
            )
            """,
            tenant_id=tenant_id,
            fb_id=fb_id,
            shipment_reference=fb_data.get("shipment_reference"),
            props={**fb_data, "tenant_id": tenant_id, "id": fb_id},
        )

    async def list_carriers(self, tenant_id: str) -> list[dict]:
        rows = await self._execute(
            "MATCH (c:Carrier {tenant_id: $tenant_id}) RETURN c.id AS id, c.name AS name",
            tenant_id=normalize_tenant_id(tenant_id),
        )
        return rows

    async def get_carrier_node(self, tenant_id: str, carrier_id: str) -> dict | None:
        rows = await self._execute(
            "MATCH (c:Carrier {tenant_id: $tenant_id, id: $carrier_id}) RETURN properties(c) AS node",
            tenant_id=normalize_tenant_id(tenant_id),
            carrier_id=carrier_id,
        )
        return rows[0]["node"] if rows else None

    async def get_contracts_for_lane(self, tenant_id: str, carrier_id: str, lane: str) -> list[dict]:
        rows = await self._execute(
            """
            MATCH (:Carrier {tenant_id: $tenant_id, id: $carrier_id})-[:HAS_CONTRACT]->(cc:Contract)-[r:COVERS_LANE]->(:Lane {tenant_id: $tenant_id, lane: $lane})
            RETURN properties(cc) AS contract, r.rate_row AS rate_row
            """,
            tenant_id=normalize_tenant_id(tenant_id),
            carrier_id=carrier_id,
            lane=lane,
        )
        results = []
        for row in rows:
            contract = dict(row["contract"])
            contract["matched_rate_row"] = row["rate_row"]
            results.append(contract)
        return results

    async def get_shipment_node(self, tenant_id: str, shipment_id: str) -> dict | None:
        rows = await self._execute(
            "MATCH (s:Shipment {tenant_id: $tenant_id, id: $shipment_id}) RETURN properties(s) AS node",
            tenant_id=normalize_tenant_id(tenant_id),
            shipment_id=shipment_id,
        )
        return rows[0]["node"] if rows else None

    async def get_bols_for_shipment(self, tenant_id: str, shipment_id: str) -> list[dict]:
        rows = await self._execute(
            """
            MATCH (:Shipment {tenant_id: $tenant_id, id: $shipment_id})-[:HAS_BOL]->(b:BOL)
            RETURN properties(b) AS node
            """,
            tenant_id=normalize_tenant_id(tenant_id),
            shipment_id=shipment_id,
        )
        return [row["node"] for row in rows]

    async def get_freight_bill_node(self, tenant_id: str, fb_id: str) -> dict | None:
        rows = await self._execute(
            "MATCH (fb:FreightBill {tenant_id: $tenant_id, id: $fb_id}) RETURN properties(fb) AS node",
            tenant_id=normalize_tenant_id(tenant_id),
            fb_id=fb_id,
        )
        return rows[0]["node"] if rows else None

    async def get_freight_bills_for_shipment(self, tenant_id: str, shipment_id: str) -> list[str]:
        rows = await self._execute(
            """
            MATCH (fb:FreightBill {tenant_id: $tenant_id})-[:REFERENCES]->(:Shipment {tenant_id: $tenant_id, id: $shipment_id})
            RETURN fb.id AS id
            """,
            tenant_id=normalize_tenant_id(tenant_id),
            shipment_id=shipment_id,
        )
        return [row["id"] for row in rows]

    async def find_duplicate_bill_ids(
        self,
        tenant_id: str,
        bill_number: str,
        carrier_id: str | None,
        carrier_name: str | None,
        exclude_bill_id: str,
    ) -> list[str]:
        tenant_id = normalize_tenant_id(tenant_id)
        if carrier_id:
            rows = await self._execute(
                """
                MATCH (fb:FreightBill {tenant_id: $tenant_id, bill_number: $bill_number, carrier_id: $carrier_id})
                WHERE fb.id <> $exclude_bill_id
                RETURN fb.id AS id
                """,
                tenant_id=tenant_id,
                bill_number=bill_number,
                carrier_id=carrier_id,
                exclude_bill_id=exclude_bill_id,
            )
            return [row["id"] for row in rows]

        normalized_name = (carrier_name or "").strip().lower()
        if not normalized_name:
            return []
        rows = await self._execute(
            """
            MATCH (fb:FreightBill {tenant_id: $tenant_id, bill_number: $bill_number})
            WHERE fb.id <> $exclude_bill_id AND toLower(trim(fb.carrier_name)) = $carrier_name
            RETURN fb.id AS id
            """,
            tenant_id=tenant_id,
            bill_number=bill_number,
            carrier_name=normalized_name,
            exclude_bill_id=exclude_bill_id,
        )
        return [row["id"] for row in rows]


class GraphService:
    def __init__(self, backend: GraphBackend | None = None) -> None:
        self.backend = backend or MemoryGraphBackend()
        self._built_tenants: set[str] = set()

    async def build(self, db: AsyncSession, tenant_id: str = "default") -> None:
        tenant_id = normalize_tenant_id(tenant_id)
        await self.backend.build(db, tenant_id)
        self._built_tenants.add(tenant_id)

    async def ensure_built(self, db: AsyncSession, tenant_id: str = "default") -> None:
        tenant_id = normalize_tenant_id(tenant_id)
        if tenant_id not in self._built_tenants:
            await self.build(db, tenant_id)

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

    async def health(self) -> dict:
        return await self.backend.health()


_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        backend_name = (settings.graph_backend or "memory").strip().lower()
        if backend_name == "neo4j" and settings.neo4j_password:
            _graph_service = GraphService(Neo4jGraphBackend())
        else:
            if backend_name == "neo4j":
                logger.warning("Neo4j graph backend requested but NEO4J_PASSWORD is empty; using memory backend")
            _graph_service = GraphService(MemoryGraphBackend())
    return _graph_service
