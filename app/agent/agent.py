"""
Freight Bill Processing Agent
==============================
A LangGraph stateful agent with the following node flow:

  START
    │
    ▼
  [load_context]          ← fetch carrier, contracts, shipment, BOLs from graph
    │
    ▼
  [validate]              ← run all deterministic rules from rules.py
    │
    ▼
  [resolve_ambiguity]     ← if multiple contracts match, use LLM to pick one
    │
    ▼
  [decide]                ← compute confidence, emit decision
    │
    ├─── confidence >= threshold ──► [finalize] ──► END
    │
    └─── confidence < threshold  ──► [human_review] ←── interrupt()
                                          │
                                          └──► [finalize] ──► END

State is persisted via LangGraph's MemorySaver (dev) or AsyncPostgresSaver (prod).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from app.config import get_settings
from app.services.graph_service import get_graph_service
from app.agent import rules
from app.agent.rules import ValidationResult, Finding, compute_confidence
from app.agent import llm_service

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    bill: dict                          # raw freight bill dict
    bill_id: str

    # Context gathered during load_context
    carrier: dict | None
    carrier_id: str | None
    all_candidate_contracts: list[dict]
    chosen_contract: dict | None
    shipment: dict | None
    bols: list[dict]
    prior_billed_weight: float
    existing_bill_ids: list[str]        # for duplicate check

    # Validation
    findings: Annotated[list[dict], operator.add]   # accumulate across nodes
    ambiguity_note: str | None

    # Decision
    confidence: float
    decision: str | None                # auto_approve | flag | dispute
    explanation: str | None

    # Human review
    reviewer_decision: str | None
    reviewer_notes: str | None

    # Audit trail
    audit: Annotated[list[dict], operator.add]


def _finding_to_dict(f: Finding) -> dict:
    return {"code": f.code, "severity": f.severity, "message": f.message, "detail": f.detail}


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Node: load_context ────────────────────────────────────────────────────────

async def load_context(state: AgentState) -> dict:
    """
    Traverse the in-memory graph to pull all data needed for validation:
    carrier, contracts covering the bill's lane, shipment, BOLs,
    and any prior freight bills for the same shipment.
    """
    graph = get_graph_service()
    bill = state["bill"]
    bill_id = state["bill_id"]

    audit = [{"event": "load_context_start", "bill_id": bill_id, "ts": _now()}]

    # ── Carrier resolution ────────────────────────────────────────────────────
    carrier_id = bill.get("carrier_id")
    carrier = None

    if carrier_id:
        carrier = graph.get_carrier_node(carrier_id)

    # If no carrier_id or not found, try fuzzy match via LLM
    if not carrier and bill.get("carrier_name"):
        all_carriers_proper = []
        for nid, ndata in graph.G.nodes(data=True):
            if ndata.get("type") == "carrier":
                all_carriers_proper.append({
                    "id": nid.replace("carrier:", ""),
                    "name": ndata.get("name", ""),
                })

        matched_id = await llm_service.normalize_carrier_name(
            bill["carrier_name"], all_carriers_proper
        )
        if matched_id:
            carrier_id = matched_id
            carrier = graph.get_carrier_node(carrier_id)
            audit.append({"event": "carrier_fuzzy_matched", "matched_to": carrier_id, "ts": _now()})

    # ── Contract resolution ───────────────────────────────────────────────────
    candidate_contracts: list[dict] = []
    if carrier_id and bill.get("lane"):
        candidate_contracts = graph.get_contracts_for_lane(carrier_id, bill["lane"])

    # ── Shipment + BOL ────────────────────────────────────────────────────────
    shipment = None
    bols: list[dict] = []
    if bill.get("shipment_reference"):
        shipment = graph.get_shipment_node(bill["shipment_reference"])
        if shipment:
            bols = graph.get_bols_for_shipment(bill["shipment_reference"])

    # ── Prior bills for same shipment (over-billing check) ────────────────────
    prior_billed_weight = 0.0
    dup_ids: list[str] = []

    if bill.get("shipment_reference"):
        prior_fb_ids = graph.get_freight_bills_for_shipment(bill["shipment_reference"])
        prior_fb_ids = [fid for fid in prior_fb_ids if fid != bill_id]

        for fid in prior_fb_ids:
            fb_node = graph.G.nodes.get(f"fb:{fid}", {})
            prior_billed_weight += fb_node.get("billed_weight_kg", 0)

    # ── Duplicate check: same bill_number across all freight bills in graph ───
    bill_number = bill.get("bill_number", "")
    incoming_carrier_id = carrier_id or bill.get("carrier_id")
    incoming_carrier_name = (bill.get("carrier_name") or "").strip().lower()
    for nid, ndata in graph.G.nodes(data=True):
        node_carrier_id = ndata.get("carrier_id")
        node_carrier_name = (ndata.get("carrier_name") or "").strip().lower()
        same_carrier = False
        if incoming_carrier_id and node_carrier_id:
            same_carrier = incoming_carrier_id == node_carrier_id
        elif incoming_carrier_name and node_carrier_name:
            same_carrier = incoming_carrier_name == node_carrier_name
        else:
            same_carrier = not incoming_carrier_id and not incoming_carrier_name

        if (
            ndata.get("type") == "freight_bill"
            and ndata.get("bill_number") == bill_number
            and same_carrier
            and ndata.get("id") != bill_id
        ):
            dup_ids.append(ndata.get("id", nid))

    audit.append({
        "event": "context_loaded",
        "carrier_id": carrier_id,
        "contracts_found": len(candidate_contracts),
        "shipment": shipment.get("id") if shipment else None,
        "bols": len(bols),
        "prior_billed_weight": prior_billed_weight,
        "duplicates_found": dup_ids,
        "ts": _now(),
    })

    return {
        "carrier": carrier,
        "carrier_id": carrier_id,
        "all_candidate_contracts": candidate_contracts,
        "chosen_contract": None,
        "shipment": shipment,
        "bols": bols,
        "prior_billed_weight": prior_billed_weight,
        "existing_bill_ids": dup_ids,
        "findings": [],
        "ambiguity_note": None,
        "audit": audit,
    }


# ── Node: validate ────────────────────────────────────────────────────────────

async def validate(state: AgentState) -> dict:
    """
    Run all deterministic rule checks that don't require contract disambiguation.
    Contract-dependent checks (rate, FSC, base charge) are run here with the first
    candidate and then re-run in resolve_ambiguity once the chosen contract is known.
    """
    bill = state["bill"]
    findings: list[dict] = []

    # 1. Duplicate bill check
    findings.append(_finding_to_dict(rules.check_duplicate(
        bill.get("bill_number", ""),
        state.get("carrier_id", "") or "",
        state.get("existing_bill_ids", []),
    )))

    # 2. Carrier known in system
    findings.append(_finding_to_dict(
        rules.check_carrier_known(state.get("carrier_id"), bill.get("carrier_name", ""))
    ))

    # 3. Internal total consistency (base + fsc + gst = total)
    findings.append(_finding_to_dict(rules.check_total_amount(bill)))

    # 4. Contract checks — preliminary pass with the first candidate
    #    resolve_ambiguity will re-run these with the chosen contract
    candidates = state.get("all_candidate_contracts", [])
    first_contract = candidates[0] if candidates else None

    findings.append(_finding_to_dict(
        rules.check_contract_active(first_contract, bill.get("bill_date", ""))
    ))

    if first_contract:
        rate_row = first_contract.get("matched_rate_row") or {}
        findings.append(_finding_to_dict(rules.check_rate(bill, rate_row, bill.get("bill_date", ""))))
        findings.append(_finding_to_dict(rules.check_fuel_surcharge(bill, rate_row, bill.get("bill_date", ""))))
        findings.append(_finding_to_dict(rules.check_base_charge(bill, rate_row)))
        findings.append(_finding_to_dict(rules.check_uom_mismatch(bill, rate_row)))

    # 5. Weight vs BOL (always deterministic — not contract-dependent)
    findings.append(_finding_to_dict(rules.check_weight_vs_bol(
        bill,
        state.get("bols", []),
        state.get("prior_billed_weight", 0.0),
    )))

    audit = [{"event": "validation_complete", "finding_count": len(findings), "ts": _now()}]
    return {"findings": findings, "audit": audit}


# ── Node: resolve_ambiguity ───────────────────────────────────────────────────

async def resolve_ambiguity(state: AgentState) -> dict:
    """
    If there is exactly one candidate contract, confirm it.
    If multiple overlap, use the LLM to pick the best match given the bill details.
    Re-runs contract-dependent checks with the chosen contract.
    """
    bill = state["bill"]
    candidates = state.get("all_candidate_contracts", [])
    audit = []

    if not candidates:
        # No contract found — nothing to resolve
        return {"chosen_contract": None, "ambiguity_note": None, "findings": [], "audit": audit}

    chosen: dict | None = None
    ambiguity_note: str | None = None

    if len(candidates) == 1:
        chosen = candidates[0]
        ambiguity_note = None
    else:
        # Filter to contracts that are active on the bill date for LLM resolution
        from app.agent.rules import _parse_date
        bd = _parse_date(bill.get("bill_date", ""))
        active_candidates = []
        for c in candidates:
            if c.get("status") == "expired":
                continue
            exp = _parse_date(c.get("expiry_date", ""))
            eff = _parse_date(c.get("effective_date", ""))
            if bd and exp and bd > exp:
                continue
            if bd and eff and bd < eff:
                continue
            active_candidates.append(c)

        if not active_candidates:
            active_candidates = candidates  # fall back to all if none are active

        chosen, reasoning = await llm_service.resolve_ambiguous_contract(bill, active_candidates)
        ambiguity_note = reasoning
        audit.append({
            "event": "contract_ambiguity_resolved",
            "candidates": [c["id"] for c in active_candidates],
            "chosen": chosen["id"] if chosen else None,
            "reasoning": reasoning,
            "ts": _now(),
        })

    if not chosen:
        return {"chosen_contract": None, "ambiguity_note": ambiguity_note, "findings": [], "audit": audit}

    # Re-run rate/charge/uom checks with the definitive chosen contract
    # These replace the preliminary checks done in validate()
    rate_row = chosen.get("matched_rate_row") or {}
    recheck_findings: list[dict] = []

    recheck_findings.append(_finding_to_dict(rules.check_contract_active(chosen, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_rate(bill, rate_row, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_fuel_surcharge(bill, rate_row, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_base_charge(bill, rate_row)))
    recheck_findings.append(_finding_to_dict(rules.check_uom_mismatch(bill, rate_row)))

    return {
        "chosen_contract": chosen,
        "ambiguity_note": ambiguity_note,
        "findings": recheck_findings,
        "audit": audit,
    }


# ── Node: decide ──────────────────────────────────────────────────────────────

async def decide(state: AgentState) -> dict:
    """
    Compute final confidence score and emit a decision.
    Ambiguous contract selection penalises confidence by 0.15.

    Decision logic:
    - auto_approve  → confidence >= threshold AND no errors
    - dispute       → confidence <= dispute_threshold OR hard-error codes present
    - flag          → everything else (goes to human review)
    """
    vr = ValidationResult()

    # De-duplicate findings: later findings (from re-check in resolve_ambiguity)
    # override earlier ones for the same code — keyed by code, last-write wins.
    all_findings = state["findings"]
    deduped: dict[str, Finding] = {}
    for fd in all_findings:
        code = fd["code"]
        deduped[code] = Finding(
            code=fd["code"],
            severity=fd["severity"],
            message=fd["message"],
            detail=fd.get("detail", {}),
        )
    for f in deduped.values():
        vr.add(f)

    confidence = compute_confidence(vr)

    # Ambiguity penalty — only when there were genuine multiple candidates
    if state.get("ambiguity_note") and len(state.get("all_candidate_contracts", [])) > 1:
        confidence = round(max(0.0, confidence - 0.15), 3)

    # Hard error codes that force a dispute regardless of confidence
    dispute_codes = {"DUPLICATE_BILL", "UNKNOWN_CARRIER", "WEIGHT_MISMATCH"}
    hard_error = any(
        f.code in dispute_codes and f.severity == "error"
        for f in vr.findings
    )

    if confidence >= settings.auto_approve_threshold and not vr.errors:
        decision = "auto_approve"
    elif confidence <= settings.dispute_threshold or hard_error:
        decision = "dispute"
    else:
        decision = "flag"

    audit = [{
        "event": "decision_made",
        "decision": decision,
        "confidence": confidence,
        "error_count": len(vr.errors),
        "warn_count": len(vr.warnings),
        "ts": _now(),
    }]

    return {
        "confidence": confidence,
        "decision": decision,
        "findings": [_finding_to_dict(f) for f in deduped.values()],
        "audit": audit,
    }


# ── Node: human_review (interrupt) ───────────────────────────────────────────

async def human_review(state: AgentState) -> dict:
    """
    Pause execution using LangGraph's interrupt().
    The graph resumes when POST /review/{id} calls agent.update_state()
    with the reviewer's decision, which becomes the return value of interrupt().
    """
    logger.info(
        f"Bill {state['bill_id']} paused for human review "
        f"(confidence={state['confidence']:.2f}, decision={state['decision']})"
    )

    reviewer_input = interrupt({
        "bill_id": state["bill_id"],
        "decision": state["decision"],
        "confidence": state["confidence"],
        "summary": (
            f"Bill {state['bill_id']} needs review — "
            f"confidence {state['confidence']:.0%}, decision: {state['decision']}"
        ),
    })

    reviewer_decision = reviewer_input.get("reviewer_decision", "approve")
    reviewer_notes = reviewer_input.get("reviewer_notes", "")

    return {
        "reviewer_decision": reviewer_decision,
        "reviewer_notes": reviewer_notes,
        "audit": [{
            "event": "human_review_received",
            "reviewer_decision": reviewer_decision,
            "ts": _now(),
        }],
    }


# ── Node: finalize ────────────────────────────────────────────────────────────

async def finalize(state: AgentState) -> dict:
    """Generate a plain-English explanation and write the final decision."""
    bill_id = state["bill_id"]
    decision = state.get("reviewer_decision") or state.get("decision", "flag")
    confidence = state.get("confidence", 0.0)

    findings_for_llm = [
        {"severity": f["severity"], "message": f["message"]}
        for f in state.get("findings", [])
    ]

    explanation = await llm_service.generate_explanation(
        bill_id, findings_for_llm, decision, confidence
    )

    audit = [{"event": "finalized", "decision": decision, "ts": _now()}]
    return {"explanation": explanation, "decision": decision, "audit": audit}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_decide(state: AgentState) -> str:
    """
    auto_approve → finalize directly (no human needed)
    flag / dispute → human_review (interrupt, wait for POST /review/{id})
    """
    if state.get("decision") == "auto_approve":
        return "finalize"
    return "human_review"


# ── Build Graph ───────────────────────────────────────────────────────────────

def build_agent(checkpointer=None):
    """
    Build and compile the LangGraph agent.
    Pass a checkpointer to enable state persistence across interrupt/resume cycles.
    """
    builder = StateGraph(AgentState)

    builder.add_node("load_context", load_context)
    builder.add_node("validate", validate)
    builder.add_node("resolve_ambiguity", resolve_ambiguity)
    builder.add_node("decide", decide)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)

    builder.set_entry_point("load_context")
    builder.add_edge("load_context", "validate")
    builder.add_edge("validate", "resolve_ambiguity")
    builder.add_edge("resolve_ambiguity", "decide")
    builder.add_conditional_edges("decide", route_after_decide, {
        "finalize": "finalize",
        "human_review": "human_review",
    })
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


# ── Singleton ─────────────────────────────────────────────────────────────────
# MemorySaver for dev — swap to AsyncPostgresSaver for production so agent
# state survives restarts and can resume interrupted threads after a redeploy.

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent(MemorySaver())
    return _agent
