"""
Graph Service
=============
Builds an in-memory directed graph (NetworkX) from the relational data at
startup and provides query helpers for the agent.

Node types:  Carrier, Contract, Lane, Shipment, BOL, FreightBill
Edge types:  has_contract, covers_lane, has_shipment, has_bol, references

This lets the agent traverse relationships without writing multi-join SQL for
every query. The graph is rebuilt on startup and can be refreshed on demand.
"""

from __future__ import annotations
import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db_models import Carrier, CarrierContract, Shipment, BillOfLading


class GraphService:
    def __init__(self):
        self.G: nx.DiGraph = nx.DiGraph()

    # ── Build ─────────────────────────────────────────────────────────────────

    async def build(self, db: AsyncSession) -> None:
        """Load all reference data from Postgres and construct the graph."""
        G = nx.DiGraph()

        # Carriers
        carriers = (await db.execute(select(Carrier))).scalars().all()
        for c in carriers:
            G.add_node(f"carrier:{c.id}", type="carrier", **{
                "name": c.name, "code": c.carrier_code, "status": c.status
            })

        # Contracts
        contracts = (await db.execute(select(CarrierContract))).scalars().all()
        for cc in contracts:
            node_id = f"contract:{cc.id}"
            G.add_node(node_id, type="contract", **{
                "id": cc.id,
                "carrier_id": cc.carrier_id,
                "effective_date": cc.effective_date,
                "expiry_date": cc.expiry_date,
                "status": cc.status,
                "rate_card": cc.rate_card,
                "notes": cc.notes,
            })
            G.add_edge(f"carrier:{cc.carrier_id}", node_id, rel="has_contract")

            # Lane nodes
            for rate_row in cc.rate_card:
                lane = rate_row.get("lane")
                if lane:
                    lane_node = f"lane:{lane}"
                    if not G.has_node(lane_node):
                        G.add_node(lane_node, type="lane", lane=lane)
                    G.add_edge(node_id, lane_node, rel="covers_lane", rate_row=rate_row)

        # Shipments
        shipments = (await db.execute(select(Shipment))).scalars().all()
        for s in shipments:
            node_id = f"shipment:{s.id}"
            G.add_node(node_id, type="shipment", **{
                "id": s.id,
                "carrier_id": s.carrier_id,
                "contract_id": s.contract_id,
                "lane": s.lane,
                "shipment_date": s.shipment_date,
                "status": s.status,
                "total_weight_kg": s.total_weight_kg,
            })
            G.add_edge(f"carrier:{s.carrier_id}", node_id, rel="has_shipment")
            if s.contract_id:
                G.add_edge(f"contract:{s.contract_id}", node_id, rel="has_shipment")

        # BOLs
        bols = (await db.execute(select(BillOfLading))).scalars().all()
        for b in bols:
            node_id = f"bol:{b.id}"
            G.add_node(node_id, type="bol", **{
                "id": b.id,
                "shipment_id": b.shipment_id,
                "delivery_date": b.delivery_date,
                "actual_weight_kg": b.actual_weight_kg,
            })
            G.add_edge(f"shipment:{b.shipment_id}", node_id, rel="has_bol")

        self.G = G

    def add_freight_bill(self, fb_id: str, fb_data: dict) -> None:
        """Add a freight bill node and wire it to its shipment if referenced."""
        node_id = f"fb:{fb_id}"
        self.G.add_node(node_id, type="freight_bill", **fb_data)
        if fb_data.get("shipment_reference"):
            shp_node = f"shipment:{fb_data['shipment_reference']}"
            if self.G.has_node(shp_node):
                self.G.add_edge(node_id, shp_node, rel="references")

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_carrier_node(self, carrier_id: str) -> dict | None:
        return self.G.nodes.get(f"carrier:{carrier_id}")

    def get_contracts_for_carrier(self, carrier_id: str) -> list[dict]:
        contracts = []
        carrier_node = f"carrier:{carrier_id}"
        for _, target, data in self.G.out_edges(carrier_node, data=True):
            if data.get("rel") == "has_contract":
                contracts.append(self.G.nodes[target])
        return contracts

    def get_contracts_for_lane(self, carrier_id: str, lane: str) -> list[dict]:
        """Contracts for a carrier that cover a specific lane, with matched rate row."""
        results = []
        carrier_node = f"carrier:{carrier_id}"
        for _, contract_node, data in self.G.out_edges(carrier_node, data=True):
            if data.get("rel") != "has_contract":
                continue
            for _, lane_node, edge_data in self.G.out_edges(contract_node, data=True):
                if (
                    edge_data.get("rel") == "covers_lane"
                    and self.G.nodes[lane_node].get("lane") == lane
                ):
                    contract_data = dict(self.G.nodes[contract_node])
                    contract_data["matched_rate_row"] = edge_data.get("rate_row")
                    results.append(contract_data)
        return results

    def get_shipment_node(self, shipment_id: str) -> dict | None:
        return self.G.nodes.get(f"shipment:{shipment_id}")

    def get_bols_for_shipment(self, shipment_id: str) -> list[dict]:
        bols = []
        shp_node = f"shipment:{shipment_id}"
        for _, bol_node, data in self.G.out_edges(shp_node, data=True):
            if data.get("rel") == "has_bol":
                bols.append(dict(self.G.nodes[bol_node]))
        return bols

    def get_freight_bills_for_shipment(self, shipment_id: str) -> list[str]:
        """Freight bill IDs that reference a given shipment (for over-billing checks)."""
        shp_node = f"shipment:{shipment_id}"
        fb_ids = []
        for source, target, data in self.G.in_edges(shp_node, data=True):
            if data.get("rel") == "references" and self.G.nodes[source].get("type") == "freight_bill":
                fb_ids.append(self.G.nodes[source].get("id", source.replace("fb:", "")))
        return fb_ids


# Singleton
_graph_service: GraphService | None = None


def get_graph_service() -> GraphService:
    global _graph_service
    if _graph_service is None:
        _graph_service = GraphService()
    return _graph_service