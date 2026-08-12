"""
Demo data generation and cleanup.

Demo records are deterministic and isolated with DEMO/CAR-DEMO prefixes so they
can be safely loaded, processed, and removed without touching assignment seed
data or user-created bills.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenancy import normalize_tenant_id
from app.models.db_models import (
    AuditLog,
    BillOfLading,
    Company,
    Carrier,
    CarrierContract,
    FreightBill,
    FreightBillStatus,
    PartnerFirm,
    Shipment,
)

DEMO_BILL_COUNT = 120
DEMO_DETERMINISTIC_COUNT = 60
DEMO_LLM_COUNT = 40
DEMO_ANOMALY_COUNT = 20

# The edge portfolio is intentionally explicit. It doubles as executable
# product documentation: each record carries its scenario and expected path in
# FreightBill.evidence, so operators can understand what a demo result proves.
DEMO_EDGE_SCENARIOS = (
    "rate_outlier",
    "weight_overbill",
    "duplicate_number",
    "duplicate_number",
    "total_mismatch",
    "fuel_surcharge_mismatch",
    "expired_contract",
    "future_contract",
    "minimum_weight_not_met",
    "missing_bol",
    "missing_shipment_reference",
    "no_matching_contract",
    "uom_mismatch",
    "base_charge_mismatch",
    "rate_warning",
    "underbilled_weight",
    "unknown_carrier",
    "revised_fuel_surcharge",
    "minimum_charge_applied",
    "multiple_bols",
)

DEMO_SCENARIO_EXPECTATIONS = {
    "rate_outlier": "Dispute after deterministic and graph rate checks detect a material overcharge.",
    "weight_overbill": "Dispute because billed weight exceeds connected BOL evidence.",
    "duplicate_number": "Establish one canonical bill and reject the paired bill that reuses its carrier bill number.",
    "total_mismatch": "Do not call the LLM; surface an internally inconsistent invoice total.",
    "fuel_surcharge_mismatch": "Surface an incorrect fuel surcharge while keeping the invoice total internally consistent.",
    "expired_contract": "Surface a contract explicitly marked expired.",
    "future_contract": "Surface a contract whose effective date is after the bill date.",
    "minimum_weight_not_met": "Surface failure to meet the selected rate row's minimum weight.",
    "missing_bol": "Reduce confidence and route missing delivery evidence according to thresholds.",
    "missing_shipment_reference": "Reduce confidence because shipment traversal and BOL evidence are unavailable.",
    "no_matching_contract": "Surface the absence of a carrier-and-lane contract.",
    "uom_mismatch": "Pause for review when a per-kg bill is evaluated against an FTL-only contract.",
    "base_charge_mismatch": "Surface a base charge that does not equal the contracted calculation.",
    "rate_warning": "Accept a small rate variance as a warning rather than a hard rate error.",
    "underbilled_weight": "Warn when billed weight is below BOL evidence rather than treating it as overbilling.",
    "unknown_carrier": "Dispute an explicit carrier identifier that is not present in reference data.",
    "revised_fuel_surcharge": "Apply the revised surcharge percentage effective on the bill date.",
    "minimum_charge_applied": "Accept the contractual minimum charge when weight multiplied by rate is lower.",
    "multiple_bols": "Aggregate multiple BOL records before comparing delivered and billed weight.",
}


def _money(value: float) -> float:
    return round(value, 2)


def _bill_amounts(weight: float, rate: float, fsc_percent: float) -> tuple[float, float, float, float]:
    base = _money(weight * rate)
    fsc = _money(base * fsc_percent / 100)
    gst = _money((base + fsc) * 0.18)
    total = _money(base + fsc + gst)
    return base, fsc, gst, total


def build_demo_dataset(tenant_id: str | None = None) -> dict[str, list[dict]]:
    """Build the full demo freight-bill portfolio and reference records."""
    tenant_id = normalize_tenant_id(tenant_id)
    # Most application IDs are currently global primary keys even though all
    # business reads are tenant-scoped. Include a stable tenant fingerprint so
    # two tenants can load the synthetic portfolio without primary-key clashes.
    tenant_fingerprint = sha256(tenant_id.encode("utf-8")).hexdigest()[:8].upper()
    demo_scope = f"{tenant_id[:12].upper()}-{tenant_fingerprint}"
    partner_firm_id = f"DEMO-CA-FIRM-{demo_scope}-001"
    company_id = f"DEMO-COMPANY-{demo_scope}-001"
    carrier_ids = [f"CAR-DEMO-{demo_scope}-{index:03d}" for index in range(1, 5)]

    partner_firms = [{
        "tenant_id": tenant_id,
        "id": partner_firm_id,
        "name": "Demo Ledger Assurance LLP",
        "firm_type": "ca_firm",
        "registration_number": "FRN-DEMO-001",
        "gstin": "27DEMOCA001Z5",
        "contact_name": "Asha Mehta",
        "contact_email": "asha.mehta@demo-ledger.example",
        "contact_phone": "+91-90000-00001",
        "status": "active",
    }]
    companies = [{
        "tenant_id": tenant_id,
        "id": company_id,
        "legal_name": "Demo Freight Operating Company Private Limited",
        "display_name": "Demo FreightCo",
        "gstin": "27DEMOFRT001Z2",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "billing_email": "finance@demo-freightco.example",
        "status": "active",
        "ca_partner_firm_id": partner_firm_id,
    }]
    carriers = [
        {
            "tenant_id": tenant_id,
            "id": carrier_ids[0],
            "name": "Demo Atlas Freight",
            "carrier_code": "DAT",
            "gstin": "27DEMO0001A1Z1",
            "bank_account": "DEMO-ATLAS-001",
            "status": "active",
            "onboarded_on": "2024-01-01",
        },
        {
            "tenant_id": tenant_id,
            "id": carrier_ids[1],
            "name": "Demo Northline Logistics",
            "carrier_code": "DNL",
            "gstin": "27DEMO0002A1Z2",
            "bank_account": "DEMO-NORTH-002",
            "status": "active",
            "onboarded_on": "2024-02-01",
        },
        {
            "tenant_id": tenant_id,
            "id": carrier_ids[2],
            "name": "Demo Meridian Transport",
            "carrier_code": "DMT",
            "gstin": "27DEMO0003A1Z3",
            "bank_account": "DEMO-MERIDIAN-003",
            "status": "active",
            "onboarded_on": "2024-03-01",
        },
        {
            "tenant_id": tenant_id,
            "id": carrier_ids[3],
            "name": "Demo Skyline Cargo",
            "carrier_code": "DSC",
            "gstin": "27DEMO0004A1Z4",
            "bank_account": "DEMO-SKYLINE-004",
            "status": "active",
            "onboarded_on": "2024-04-01",
        },
    ]

    contracts: list[dict] = []
    shipments: list[dict] = []
    bols: list[dict] = []
    freight_bills: list[dict] = []

    base_lanes = [
        ("DEL-JAI", 9.50, 500, carrier_ids[0]),
        ("BOM-SUR", 8.75, 640, carrier_ids[1]),
        ("BLR-MYS", 7.20, 720, carrier_ids[2]),
        ("HYD-VIJ", 8.10, 830, carrier_ids[3]),
        ("PUN-NAG", 9.80, 910, carrier_ids[0]),
        ("CHN-CBE", 7.90, 1000, carrier_ids[1]),
        ("KOL-BBS", 8.60, 1120, carrier_ids[2]),
        ("AHM-UDA", 6.90, 1250, carrier_ids[3]),
        ("LKO-VNS", 5.80, 1390, carrier_ids[0]),
        ("IND-UJN", 6.40, 1500, carrier_ids[1]),
    ]
    deterministic_lanes = [
        (f"{lane}-{idx + 1:03d}", _money(rate + (idx % 5) * 0.15), weight + (idx % 7) * 35, carrier_id)
        for idx in range(DEMO_DETERMINISTIC_COUNT)
        for lane, rate, weight, carrier_id in [base_lanes[idx % len(base_lanes)]]
    ]

    for idx, (lane, rate, weight, carrier_id) in enumerate(deterministic_lanes, start=1):
        contract_id = f"DEMO-CC-{demo_scope}-DET-{idx:03d}"
        shipment_id = f"DEMO-SHP-{demo_scope}-{idx:03d}"
        bol_id = f"DEMO-BOL-{demo_scope}-{idx:03d}"
        bill_id = f"DEMO-FB-{demo_scope}-{idx:03d}"
        fsc_percent = 7 + (idx % 3)
        base, fsc, gst, total = _bill_amounts(weight, rate, fsc_percent)
        carrier_name = next(c["name"] for c in carriers if c["id"] == carrier_id)

        contracts.append({
            "tenant_id": tenant_id,
            "id": contract_id,
            "carrier_id": carrier_id,
            "effective_date": "2025-01-01",
            "expiry_date": "2025-12-31",
            "status": "active",
            "notes": "Demo deterministic single-contract lane",
            "rate_card": [{
                "lane": lane,
                "description": f"Demo deterministic lane {lane}",
                "rate_per_kg": rate,
                "min_charge": 1000.00,
                "fuel_surcharge_percent": fsc_percent,
            }],
        })
        shipments.append({
            "tenant_id": tenant_id,
            "id": shipment_id,
            "carrier_id": carrier_id,
            "contract_id": contract_id,
            "lane": lane,
            "shipment_date": "2025-06-01",
            "status": "delivered",
            "total_weight_kg": weight,
            "notes": "Demo deterministic shipment",
        })
        bols.append({
            "tenant_id": tenant_id,
            "id": bol_id,
            "shipment_id": shipment_id,
            "delivery_date": "2025-06-03",
            "actual_weight_kg": weight,
            "notes": "Demo deterministic BOL",
        })
        freight_bills.append({
            "tenant_id": tenant_id,
            "id": bill_id,
            "carrier_id": carrier_id,
            "carrier_name": carrier_name,
            "bill_number": f"DEMO/DET/{idx:03d}",
            "bill_date": "2025-06-05",
            "shipment_reference": shipment_id,
            "lane": lane,
            "billed_weight_kg": weight,
            "rate_per_kg": rate,
            "billing_unit": "kg",
            "base_charge": base,
            "fuel_surcharge": fsc,
            "gst_amount": gst,
            "total_amount": total,
            "demo_category": "deterministic",
            "demo_kind": "deterministic",
            "demo_expectation": "Auto-approve a clean single-contract bill with complete evidence.",
        })

    base_llm_lanes = [
        ("DEL-AGR", 12.20, 1040, carrier_ids[0], "Atlas Freight Demo"),
        ("BOM-NAS", 11.40, 1180, carrier_ids[1], "Northline Demo Logistics"),
        ("BLR-HUB", 10.60, 1260, carrier_ids[2], "Meridian Demo Transport"),
        ("HYD-WGL", 9.90, 1340, carrier_ids[3], "Skyline Demo Cargo"),
        ("PUN-GOA", 13.10, 1420, carrier_ids[0], "Atlas Demo Freight Services"),
        ("CHN-MDU", 8.80, 1500, carrier_ids[1], "Northline Logistics Demo"),
        ("KOL-RNC", 12.70, 1660, carrier_ids[2], "Meridian Transport Demo"),
        ("AHM-UDA", 10.30, 1740, carrier_ids[3], "Skyline Cargo Demo"),
        ("LKO-VNS", 7.70, 1820, carrier_ids[0], "Demo Atlas Freight Co"),
        ("IND-UJN", 8.40, 1900, carrier_ids[1], "Demo Northline Freight"),
    ]
    llm_lanes = [
        (f"{lane}-{idx + 1:03d}", _money(rate + (idx % 4) * 0.2), weight + (idx % 6) * 40, carrier_id, fuzzy_name)
        for idx in range(DEMO_LLM_COUNT)
        for lane, rate, weight, carrier_id, fuzzy_name in [base_llm_lanes[idx % len(base_llm_lanes)]]
    ]

    for offset, (lane, premium_rate, weight, carrier_id, fuzzy_name) in enumerate(llm_lanes, start=1):
        idx = DEMO_DETERMINISTIC_COUNT + offset
        standard_contract_id = f"DEMO-CC-{demo_scope}-LLM-{offset:03d}-STD"
        premium_contract_id = f"DEMO-CC-{demo_scope}-LLM-{offset:03d}-PRM"
        shipment_id = f"DEMO-SHP-{demo_scope}-{idx:03d}"
        bol_id = f"DEMO-BOL-{demo_scope}-{idx:03d}"
        bill_id = f"DEMO-FB-{demo_scope}-{idx:03d}"
        fsc_percent = 8
        standard_rate = _money(premium_rate - 1.35)
        base, fsc, gst, total = _bill_amounts(weight, premium_rate, fsc_percent)
        requires_fuzzy_carrier = offset > DEMO_LLM_COUNT // 2

        contracts.extend([
            {
                "tenant_id": tenant_id,
                "id": standard_contract_id,
                "carrier_id": carrier_id,
                "effective_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "status": "active",
                "notes": "Demo standard contract; intentionally overlaps premium contract",
                "rate_card": [{
                    "lane": lane,
                    "description": f"Demo standard overlapping lane {lane}",
                    "rate_per_kg": standard_rate,
                    "min_charge": 1200.00,
                    "fuel_surcharge_percent": fsc_percent,
                }],
            },
            {
                "tenant_id": tenant_id,
                "id": premium_contract_id,
                "carrier_id": carrier_id,
                "effective_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "status": "active",
                "notes": "Demo premium express contract; bill rate is designed to match this contract",
                "rate_card": [{
                    "lane": lane,
                    "description": f"Demo premium overlapping lane {lane}",
                    "rate_per_kg": premium_rate,
                    "min_charge": 1200.00,
                    "min_weight_kg": 1000,
                    "fuel_surcharge_percent": fsc_percent,
                }],
            },
        ])
        shipments.append({
            "tenant_id": tenant_id,
            "id": shipment_id,
            "carrier_id": carrier_id,
            "contract_id": premium_contract_id,
            "lane": lane,
            "shipment_date": "2025-07-01",
            "status": "delivered",
            "total_weight_kg": weight,
            "notes": (
                "Demo AI path shipment with fuzzy carrier normalization"
                if requires_fuzzy_carrier else
                "Demo AI path shipment with known carrier and overlapping contracts"
            ),
        })
        bols.append({
            "tenant_id": tenant_id,
            "id": bol_id,
            "shipment_id": shipment_id,
            "delivery_date": "2025-07-04",
            "actual_weight_kg": weight,
            "notes": "Demo LLM path BOL",
        })
        freight_bills.append({
            "tenant_id": tenant_id,
            "id": bill_id,
            "carrier_id": None if requires_fuzzy_carrier else carrier_id,
            "carrier_name": fuzzy_name,
            "bill_number": f"DEMO/LLM/{offset:03d}",
            "bill_date": "2025-07-06",
            "shipment_reference": shipment_id,
            "lane": lane,
            "billed_weight_kg": weight,
            "rate_per_kg": premium_rate,
            "billing_unit": "kg",
            "base_charge": base,
            "fuel_surcharge": fsc,
            "gst_amount": gst,
            "total_amount": total,
            "demo_category": "llm",
            "demo_kind": "fuzzy_carrier_and_contract" if requires_fuzzy_carrier else "contract_ambiguity",
            "demo_expectation": (
                "Normalize the fuzzy carrier name, then resolve the overlapping contract."
                if requires_fuzzy_carrier else
                "Resolve two overlapping contracts; use the closest-rate fallback when no model provider is configured."
            ),
        })

    edge_blueprints = [
        ("DEL-RT", 9.50, 720, carrier_ids[0], kind)
        if kind == "rate_outlier" else
        ("BOM-WT", 8.75, 900, carrier_ids[1], kind)
        if kind == "weight_overbill" else
        ("BLR-DUP", 7.20, 840, carrier_ids[2], kind)
        if kind == "duplicate_number" else
        ("HYD-TOT", 8.10, 950, carrier_ids[3], kind)
        if kind == "total_mismatch" else
        ("PUN-FSC", 9.80, 910, carrier_ids[0], kind)
        if kind == "fuel_surcharge_mismatch" else
        ("CHN-EXP", 7.90, 1000, carrier_ids[1], kind)
        if kind == "expired_contract" else
        ("KOL-FUT", 8.60, 1120, carrier_ids[2], kind)
        if kind == "future_contract" else
        ("AHM-MIN", 6.90, 600, carrier_ids[3], kind)
        if kind == "minimum_weight_not_met" else
        ("LKO-NOBOL", 5.80, 1390, carrier_ids[0], kind)
        if kind == "missing_bol" else
        ("IND-NOREF", 6.40, 1500, carrier_ids[1], kind)
        if kind == "missing_shipment_reference" else
        ("DEL-NOCON", 10.10, 780, carrier_ids[2], kind)
        if kind == "no_matching_contract" else
        ("BOM-FTL", 1.00, 1, carrier_ids[3], kind)
        if kind == "uom_mismatch" else
        ("BLR-BASE", 7.50, 880, carrier_ids[0], kind)
        if kind == "base_charge_mismatch" else
        ("HYD-WARN", 8.40, 960, carrier_ids[1], kind)
        if kind == "rate_warning" else
        ("PUN-UNDER", 9.20, 750, carrier_ids[2], kind)
        if kind == "underbilled_weight" else
        ("CHN-UNK", 8.20, 1040, carrier_ids[3], kind)
        if kind == "unknown_carrier" else
        ("KOL-REV", 8.90, 1160, carrier_ids[0], kind)
        if kind == "revised_fuel_surcharge" else
        ("AHM-MINC", 9.00, 40, carrier_ids[1], kind)
        if kind == "minimum_charge_applied" else
        ("LKO-MBOL", 6.20, 1280, carrier_ids[2], kind)
        for kind in DEMO_EDGE_SCENARIOS
    ]
    for offset, (lane, rate, weight, carrier_id, anomaly_kind) in enumerate(edge_blueprints, start=1):
        idx = DEMO_DETERMINISTIC_COUNT + DEMO_LLM_COUNT + offset
        contract_id = f"DEMO-CC-{demo_scope}-ANOM-{offset:03d}"
        shipment_id = f"DEMO-SHP-{demo_scope}-{idx:03d}"
        bol_id = f"DEMO-BOL-{demo_scope}-{idx:03d}"
        bill_id = f"DEMO-FB-{demo_scope}-{idx:03d}"
        carrier_name = next(c["name"] for c in carriers if c["id"] == carrier_id)
        billed_rate = _money(rate * 1.45) if anomaly_kind == "rate_outlier" else rate
        if anomaly_kind == "rate_warning":
            billed_rate = _money(rate * 1.035)
        bol_weight = weight - 260 if anomaly_kind == "weight_overbill" else weight
        if anomaly_kind == "underbilled_weight":
            bol_weight = weight + 250

        fsc_percent = 9
        billed_fsc_percent = fsc_percent
        min_charge = 1000.00
        if anomaly_kind == "revised_fuel_surcharge":
            fsc_percent = 7
            billed_fsc_percent = 13

        calculation_rate = rate if anomaly_kind == "rate_warning" else billed_rate
        base, fsc, gst, total = _bill_amounts(weight, calculation_rate, billed_fsc_percent)
        if anomaly_kind == "minimum_charge_applied":
            base = min_charge
            fsc = _money(base * fsc_percent / 100)
            gst = _money((base + fsc) * 0.18)
            total = _money(base + fsc + gst)
        if anomaly_kind == "uom_mismatch":
            base = 5000.00
            fsc = _money(base * fsc_percent / 100)
            gst = _money((base + fsc) * 0.18)
            total = _money(base + fsc + gst)
        if anomaly_kind == "base_charge_mismatch":
            base = _money(base + 500)
            fsc = _money(base * fsc_percent / 100)
            gst = _money((base + fsc) * 0.18)
            total = _money(base + fsc + gst)
        if anomaly_kind == "fuel_surcharge_mismatch":
            fsc = _money(fsc * 1.45)
            gst = _money((base + fsc) * 0.18)
            total = _money(base + fsc + gst)
        if anomaly_kind == "total_mismatch":
            total = _money(total + 777)

        rate_row = {
            "lane": lane,
            "description": f"Demo edge-case lane {lane}",
            "rate_per_kg": rate,
            "min_charge": min_charge,
            "fuel_surcharge_percent": fsc_percent,
        }
        if anomaly_kind == "minimum_weight_not_met":
            rate_row["min_weight_kg"] = 1000
        if anomaly_kind == "revised_fuel_surcharge":
            rate_row.update({
                "revised_on": "2025-07-01",
                "revised_fuel_surcharge_percent": 13,
            })
        if anomaly_kind == "uom_mismatch":
            rate_row.pop("rate_per_kg")
            rate_row.update({"unit": "FTL", "rate_per_unit": 5000.00})

        has_contract = anomaly_kind not in {"no_matching_contract", "unknown_carrier"}
        if has_contract:
            contracts.append({
                "tenant_id": tenant_id,
                "id": contract_id,
                "carrier_id": carrier_id,
                "effective_date": "2026-01-01" if anomaly_kind == "future_contract" else "2025-01-01",
                "expiry_date": "2025-12-31",
                "status": "expired" if anomaly_kind == "expired_contract" else "active",
                "notes": f"Demo edge-case contract for {anomaly_kind}",
                "rate_card": [rate_row],
            })

        has_shipment = anomaly_kind != "unknown_carrier"
        if has_shipment:
            shipments.append({
                "tenant_id": tenant_id,
                "id": shipment_id,
                "carrier_id": carrier_id,
                "contract_id": contract_id if has_contract else None,
                "lane": lane,
                "shipment_date": "2025-08-01",
                "status": "delivered",
                "total_weight_kg": bol_weight,
                "notes": f"Demo edge-case shipment: {anomaly_kind}",
            })

        has_bol = has_shipment and anomaly_kind != "missing_bol"
        if has_bol:
            if anomaly_kind == "multiple_bols":
                first_weight = _money(bol_weight * 0.4)
                bol_weights = [first_weight, _money(bol_weight - first_weight)]
            else:
                bol_weights = [bol_weight]
            for bol_index, actual_weight in enumerate(bol_weights, start=1):
                bols.append({
                    "tenant_id": tenant_id,
                    "id": bol_id if bol_index == 1 else f"{bol_id}-{bol_index}",
                    "shipment_id": shipment_id,
                    "delivery_date": "2025-08-04",
                    "actual_weight_kg": actual_weight,
                    "notes": f"Demo edge-case BOL: {anomaly_kind}",
                })

        bill_carrier_id = carrier_id
        if anomaly_kind in {"duplicate_number"}:
            duplicate_occurrence = sum(
                1 for item in DEMO_EDGE_SCENARIOS[:offset]
                if item == "duplicate_number"
            )
            # One canonical row plus one carrier-name-only row avoids violating
            # the relational unique constraint while still proving duplicate
            # lookup after carrier normalization.
            bill_carrier_id = carrier_id if duplicate_occurrence == 1 else None
        elif anomaly_kind == "unknown_carrier":
            bill_carrier_id = f"CAR-DEMO-{demo_scope}-UNKNOWN"
        freight_bills.append({
            "tenant_id": tenant_id,
            "id": bill_id,
            "carrier_id": bill_carrier_id,
            "carrier_name": carrier_name,
            "bill_number": "DEMO/ANOM/DUP" if anomaly_kind == "duplicate_number" else f"DEMO/ANOM/{offset:03d}",
            "bill_date": "2025-08-06",
            "shipment_reference": None if anomaly_kind in {"missing_shipment_reference", "unknown_carrier"} else shipment_id,
            "lane": lane,
            "billed_weight_kg": weight,
            "rate_per_kg": billed_rate,
            "billing_unit": "kg",
            "base_charge": base,
            "fuel_surcharge": fsc,
            "gst_amount": gst,
            "total_amount": total,
            "demo_category": "edge",
            "demo_kind": anomaly_kind,
            "demo_expectation": DEMO_SCENARIO_EXPECTATIONS[anomaly_kind],
        })

    return {
        "partner_firms": partner_firms,
        "companies": companies,
        "carriers": carriers,
        "carrier_contracts": contracts,
        "shipments": shipments,
        "bills_of_lading": bols,
        "freight_bills": freight_bills,
    }


async def clear_demo_data(db: AsyncSession, tenant_id: str | None = None) -> dict[str, int]:
    """Remove only demo-prefixed records."""
    tenant_id = normalize_tenant_id(tenant_id)
    demo_bill_ids = select(FreightBill.id).where(
        FreightBill.tenant_id == tenant_id,
        FreightBill.id.like("DEMO-FB-%"),
    )

    audit_result = await db.execute(
        delete(AuditLog)
        .where(AuditLog.tenant_id == tenant_id, AuditLog.freight_bill_id.in_(demo_bill_ids))
        .execution_options(synchronize_session=False)
    )
    bill_result = await db.execute(
        delete(FreightBill)
        .where(FreightBill.tenant_id == tenant_id, FreightBill.id.like("DEMO-FB-%"))
        .execution_options(synchronize_session=False)
    )
    bol_result = await db.execute(
        delete(BillOfLading)
        .where(BillOfLading.tenant_id == tenant_id, BillOfLading.id.like("DEMO-BOL-%"))
        .execution_options(synchronize_session=False)
    )
    shipment_result = await db.execute(
        delete(Shipment)
        .where(Shipment.tenant_id == tenant_id, Shipment.id.like("DEMO-SHP-%"))
        .execution_options(synchronize_session=False)
    )
    contract_result = await db.execute(
        delete(CarrierContract)
        .where(CarrierContract.tenant_id == tenant_id, CarrierContract.id.like("DEMO-CC-%"))
        .execution_options(synchronize_session=False)
    )
    carrier_result = await db.execute(
        delete(Carrier)
        .where(Carrier.tenant_id == tenant_id, Carrier.id.like("CAR-DEMO%"))
        .execution_options(synchronize_session=False)
    )
    company_result = await db.execute(
        delete(Company)
        .where(Company.tenant_id == tenant_id, Company.id.like("DEMO-COMPANY-%"))
        .execution_options(synchronize_session=False)
    )
    partner_result = await db.execute(
        delete(PartnerFirm)
        .where(PartnerFirm.tenant_id == tenant_id, PartnerFirm.id.like("DEMO-CA-FIRM-%"))
        .execution_options(synchronize_session=False)
    )

    await db.commit()
    return {
        "audit_logs": audit_result.rowcount or 0,
        "freight_bills": bill_result.rowcount or 0,
        "bills_of_lading": bol_result.rowcount or 0,
        "shipments": shipment_result.rowcount or 0,
        "carrier_contracts": contract_result.rowcount or 0,
        "carriers": carrier_result.rowcount or 0,
        "companies": company_result.rowcount or 0,
        "partner_firms": partner_result.rowcount or 0,
    }


async def load_demo_data(db: AsyncSession, tenant_id: str | None = None) -> dict:
    """Clear existing demo records, load fresh demo records, and return bill payloads."""
    tenant_id = normalize_tenant_id(tenant_id)
    removed = await clear_demo_data(db, tenant_id)
    data = build_demo_dataset(tenant_id)

    for row in data["partner_firms"]:
        db.add(PartnerFirm(**row))
    await db.flush()

    for row in data["companies"]:
        db.add(Company(**row))
    await db.flush()

    for row in data["carriers"]:
        db.add(Carrier(**row))
    await db.flush()

    for row in data["carrier_contracts"]:
        db.add(CarrierContract(**row))
    await db.flush()

    for row in data["shipments"]:
        db.add(Shipment(**row))
    await db.flush()

    for row in data["bills_of_lading"]:
        db.add(BillOfLading(**row))
    await db.flush()

    bill_payloads = []
    bill_scenarios = []
    scenario_counts: Counter[str] = Counter()
    for source_row in data["freight_bills"]:
        row = dict(source_row)
        demo_category = row.pop("demo_category")
        demo_kind = row.pop("demo_kind")
        demo_expectation = row.pop("demo_expectation")
        bill_payloads.append(dict(row))
        scenario_counts[demo_kind] += 1
        bill_scenarios.append({
            "bill_id": row["id"],
            "category": demo_category,
            "scenario": demo_kind,
            "expected_behavior": demo_expectation,
        })
        db.add(FreightBill(
            **row,
            status=FreightBillStatus.pending,
            evidence={
                "demo": True,
                "demo_category": demo_category,
                "demo_kind": demo_kind,
                "expected_behavior": demo_expectation,
            },
        ))
        db.add(AuditLog(
            tenant_id=tenant_id,
            freight_bill_id=row["id"],
            event="demo_bill_loaded",
            detail={
                "source": "demo_data",
                "demo_category": demo_category,
                "demo_kind": demo_kind,
                "expected_behavior": demo_expectation,
            },
        ))

    await db.commit()
    return {
        "removed": removed,
        "loaded": {
            "carriers": len(data["carriers"]),
            "companies": len(data["companies"]),
            "partner_firms": len(data["partner_firms"]),
            "carrier_contracts": len(data["carrier_contracts"]),
            "shipments": len(data["shipments"]),
            "bills_of_lading": len(data["bills_of_lading"]),
            "freight_bills": len(bill_payloads),
            "deterministic_bills": DEMO_DETERMINISTIC_COUNT,
            "llm_bills": DEMO_LLM_COUNT,
            "anomaly_bills": DEMO_ANOMALY_COUNT,
            "scenario_counts": dict(sorted(scenario_counts.items())),
        },
        "bill_payloads": bill_payloads,
        "bill_scenarios": bill_scenarios,
    }
