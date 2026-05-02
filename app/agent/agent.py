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
from typing import TypedDict, Annotated
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

HARD_STOP_CODES_FOR_LLM = {"DUPLICATE_BILL", "UNKNOWN_CARRIER", "WEIGHT_MISMATCH", "TOTAL_INCONSISTENT"}


class AgentState(TypedDict):
    # takes input
    bill: dict                          # raw freight bill dict
    bill_id: str

    # context gathered during load_context
    carrier: dict | None
    carrier_id: str | None
    all_candidate_contracts: list[dict]
    chosen_contract: dict | None
    shipment: dict | None
    bols: list[dict]
    prior_billed_weight: float
    existing_bill_ids: list[str]

    # validation
    findings: Annotated[list[dict], operator.add]   # accumulate across nodes
    ambiguity_note: str | None

    # decision
    confidence: float
    decision: str | None                # auto_approve | flag | dispute
    explanation: str | None

    # human review
    reviewer_decision: str | None
    reviewer_notes: str | None

    # audit trail
    audit: Annotated[list[dict], operator.add]


def _finding_to_dict(f: Finding) -> dict:
    return {"code": f.code, "severity": f.severity, "message": f.message, "detail": f.detail}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _contract_is_active_for_bill(contract: dict, bill_date: str) -> bool:
    return rules.check_contract_active(contract, bill_date).severity == "ok"


def _contract_meets_min_weight(bill: dict, contract: dict) -> bool:
    rate_row = contract.get("matched_rate_row") or {}
    return rules.check_min_weight(bill, rate_row).severity != "error"



async def load_context(state: AgentState) -> dict:
    """
    Traverse the in-memory graph to pull all data needed for validation: carrier, contracts covering the bill's lane, shipment, BOLs,
    and any prior freight bills for the same shipment.
    """
    graph = get_graph_service()
    bill = state["bill"]
    bill_id = state["bill_id"]
    logger.info("[%s] Stage=load_context start", bill_id)

    audit = [{"event": "load_context_start", "bill_id": bill_id, "ts": _now()}]

    carrier_id = bill.get("carrier_id")
    carrier = None

    if carrier_id:
        carrier = graph.get_carrier_node(carrier_id)

    # If carrier_id is present but unknown, do not call LLM:
    # this is a deterministic unknown-carrier case.
    # Only fuzzy match when carrier_id is absent.
    if not carrier and not carrier_id and bill.get("carrier_name"):
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

    # Contract resolution
    candidate_contracts: list[dict] = []
    if carrier_id and bill.get("lane"):
        candidate_contracts = graph.get_contracts_for_lane(carrier_id, bill["lane"])

    #  Shipment + BOL
    shipment = None
    bols: list[dict] = []
    if bill.get("shipment_reference"):
        shipment = graph.get_shipment_node(bill["shipment_reference"])
        if shipment:
            bols = graph.get_bols_for_shipment(bill["shipment_reference"])

    # Prior bills for same shipment (over-billing check) 
    prior_billed_weight = 0.0
    dup_ids: list[str] = []

    if bill.get("shipment_reference"):
        prior_fb_ids = graph.get_freight_bills_for_shipment(bill["shipment_reference"])
        prior_fb_ids = [fid for fid in prior_fb_ids if fid != bill_id]

        for fid in prior_fb_ids:
            fb_node = graph.G.nodes.get(f"fb:{fid}", {})
            prior_billed_weight += fb_node.get("billed_weight_kg", 0)

    #  Duplicate check: same bill_number across all freight bills in graph 
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
    logger.info(
        "[%s] Stage=load_context done carrier_id=%s contracts=%d shipment=%s duplicates=%d",
        bill_id,
        carrier_id,
        len(candidate_contracts),
        shipment.get("id") if shipment else None,
        len(dup_ids),
    )

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


# Node: validate 

async def validate(state: AgentState) -> dict:
    """
    Run deterministic checks that do not depend on the final contract choice.
    Contract-dependent checks run only after resolve_ambiguity selects the contract,
    so stale findings from an arbitrary first candidate cannot affect the decision.
    """
    bill = state["bill"]
    bill_id = state["bill_id"]
    logger.info("[%s] Stage=validate start", bill_id)
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

    # 4. Weight vs BOL (always deterministic — not contract-dependent)
    findings.append(_finding_to_dict(rules.check_weight_vs_bol(
        bill,
        state.get("bols", []),
        state.get("prior_billed_weight", 0.0),
    )))

    audit = [{"event": "validation_complete", "finding_count": len(findings), "ts": _now()}]
    err_count = len([f for f in findings if f.get("severity") == "error"])
    warn_count = len([f for f in findings if f.get("severity") == "warn"])
    logger.info("[%s] Stage=validate done findings=%d errors=%d warns=%d", bill_id, len(findings), err_count, warn_count)
    return {"findings": findings, "audit": audit}


# Node: resolve_ambiguity

async def resolve_ambiguity(state: AgentState) -> dict:
    """
    If there is exactly one candidate contract, confirm it.
    If multiple overlap, use the LLM to pick the best match given the bill details.
    Re-run contract-dependent checks with the chosen contract.
    """
    bill = state["bill"]
    bill_id = state["bill_id"]
    candidates = state.get("all_candidate_contracts", [])
    audit = []
    logger.info("[%s] Stage=resolve_ambiguity start candidates=%d", bill_id, len(candidates))

    hard_blockers = [
        f for f in state.get("findings", [])
        if f.get("severity") == "error" and f.get("code") in HARD_STOP_CODES_FOR_LLM
    ]
    if hard_blockers:
        blocker_codes = sorted({f.get("code") for f in hard_blockers})
        logger.info("[%s] Stage=resolve_ambiguity skipped due to hard blockers=%s", bill_id, blocker_codes)
        audit.append({
            "event": "ambiguity_resolution_skipped",
            "reason": "hard_blocker_findings",
            "blockers": blocker_codes,
            "ts": _now(),
        })
        return {"chosen_contract": None, "ambiguity_note": None, "findings": [], "audit": audit}

    if not candidates:
        # No contract found — nothing to resolve
        logger.info("[%s] Stage=resolve_ambiguity done no candidates", bill_id)
        return {
            "chosen_contract": None,
            "ambiguity_note": None,
            "findings": [_finding_to_dict(rules.check_contract_active(None, bill.get("bill_date", "")))],
            "audit": audit,
        }

    chosen: dict | None = None
    ambiguity_note: str | None = None

    if len(candidates) == 1:
        chosen = candidates[0]
        ambiguity_note = None
    else:
        # Filter to contracts that are active and eligible on the bill date before LLM resolution.
        active_candidates = [
            c for c in candidates
            if _contract_is_active_for_bill(c, bill.get("bill_date", ""))
        ]

        if not active_candidates:
            active_candidates = candidates  # fall back to all if none are active

        eligible_candidates = [
            c for c in active_candidates
            if _contract_meets_min_weight(bill, c)
        ]
        candidates_for_resolution = eligible_candidates or active_candidates

        if len(candidates_for_resolution) != len(active_candidates):
            audit.append({
                "event": "contracts_filtered_by_min_weight",
                "before": [c["id"] for c in active_candidates],
                "after": [c["id"] for c in candidates_for_resolution],
                "ts": _now(),
            })

        chosen, reasoning = await llm_service.resolve_ambiguous_contract(bill, candidates_for_resolution)
        ambiguity_note = reasoning
        audit.append({
            "event": "contract_ambiguity_resolved",
            "candidates": [c["id"] for c in candidates_for_resolution],
            "chosen": chosen["id"] if chosen else None,
            "reasoning": reasoning,
            "ts": _now(),
        })
        logger.info("[%s] Stage=resolve_ambiguity llm_selected=%s from=%d", bill_id, chosen["id"] if chosen else None, len(candidates_for_resolution))

    if not chosen:
        logger.info("[%s] Stage=resolve_ambiguity done no chosen contract", bill_id)
        return {
            "chosen_contract": None,
            "ambiguity_note": ambiguity_note,
            "findings": [_finding_to_dict(rules.check_contract_active(None, bill.get("bill_date", "")))],
            "audit": audit,
        }

    # Run all contract-dependent checks with the definitive chosen contract.
    rate_row = chosen.get("matched_rate_row") or {}
    recheck_findings: list[dict] = []

    recheck_findings.append(_finding_to_dict(rules.check_contract_active(chosen, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_min_weight(bill, rate_row)))
    recheck_findings.append(_finding_to_dict(rules.check_rate(bill, rate_row, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_fuel_surcharge(bill, rate_row, bill.get("bill_date", ""))))
    recheck_findings.append(_finding_to_dict(rules.check_base_charge(bill, rate_row)))
    recheck_findings.append(_finding_to_dict(rules.check_uom_mismatch(bill, rate_row)))

    logger.info("[%s] Stage=resolve_ambiguity done chosen_contract=%s", bill_id, chosen.get("id"))
    return {
        "chosen_contract": chosen,
        "ambiguity_note": ambiguity_note,
        "findings": recheck_findings,
        "audit": audit,
    }


# Node: decide 

async def decide(state: AgentState) -> dict:
    """
    Compute final confidence score and emit a decision.
    Ambiguous contract selection penalises confidence by 0.15.

    Decision logic:
    - auto_approve  → confidence >= threshold AND no errors
    - dispute       → confidence <= dispute_threshold OR hard-error codes present
    - flag          → everything else (goes to human review)
    """
    bill_id = state["bill_id"]
    logger.info("[%s] Stage=decide start", bill_id)
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

    duplicate_error = any(f.code == "DUPLICATE_BILL" and f.severity == "error" for f in vr.findings)
    if duplicate_error:
        decision = "reject"
    elif confidence >= settings.auto_approve_threshold and not vr.errors:
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
    logger.info("[%s] Stage=decide done decision=%s confidence=%.3f errors=%d warns=%d", bill_id, decision, confidence, len(vr.errors), len(vr.warnings))

    return {
        "confidence": confidence,
        "decision": decision,
        "audit": audit,
    }


# Node: human_review (interrupt) 

async def human_review(state: AgentState) -> dict:
    """
    Pause execution using LangGraph's interrupt().
    The graph resumes when POST /review/{id} calls agent.update_state()
    with the reviewer's decision, which becomes the return value of interrupt().
    """
    logger.info(
        "[%s] Stage=human_review paused confidence=%.2f decision=%s",
        state["bill_id"],
        state["confidence"],
        state["decision"],
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


# Node: finalize 

async def finalize(state: AgentState) -> dict:
    """Generate a plain-English explanation and write the final decision."""
    bill_id = state["bill_id"]
    decision = state.get("reviewer_decision") or state.get("decision", "flag")
    confidence = state.get("confidence", 0.0)
    logger.info("[%s] Stage=finalize start decision=%s confidence=%.3f", bill_id, decision, confidence)

    findings_for_llm = [
        {"severity": f["severity"], "message": f["message"]}
        for f in state.get("findings", [])
    ]

    deterministic_error_codes = {
        "DUPLICATE_BILL",
        "UNKNOWN_CARRIER",
        "WEIGHT_MISMATCH",
        "TOTAL_INCONSISTENT",
    }
    hard_errors = [
        f for f in state.get("findings", [])
        if f.get("severity") == "error" and f.get("code") in deterministic_error_codes
    ]
    if hard_errors:
        top = hard_errors[0]
        explanation = (
            f"Freight bill {bill_id} {decision} due to deterministic validation failure: "
            f"{top.get('message', top.get('code'))}."
        )
        logger.info("[%s] Stage=finalize skipped LLM explanation due to hard deterministic error", bill_id)
    else:
        explanation = await llm_service.generate_explanation(
            bill_id, findings_for_llm, decision, confidence
        )

    audit = [{"event": "finalized", "decision": decision, "ts": _now()}]
    logger.info("[%s] Stage=finalize done", bill_id)
    return {"explanation": explanation, "decision": decision, "audit": audit}


# Routing 

def route_after_decide(state: AgentState) -> str:
    """
    auto_approve / dispute / reject → finalize directly (no human needed)
    flag → human_review (interrupt, wait for POST /review/{id})
    """
    if state.get("decision") in {"auto_approve", "dispute", "reject"}:
        return "finalize"
    return "human_review"


# Build Graph 

def build_agent(checkpointer=None):
    """
    Build and compile the LangGraph agent. Pass a checkpointer to enable state persistence across interrupt/resume cycles.
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
