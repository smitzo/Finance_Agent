"""
LLM Service
===========
Used only for:
1. Fuzzy carrier name normalization (match "Gati KWE Logistics" to DB carrier names)
2. Generating human-readable decision explanations from structured findings
3. Resolving ambiguous contract selection when multiple overlap

All deterministic checks (rates, weights, dates) are in rules.py.
"""

from __future__ import annotations
import json
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_llm_client():
    preferred = (settings.llm_provider or "").strip().lower()

    if preferred == "openai" and settings.openai_api_key:
        from openai import AsyncOpenAI
        return ("openai", AsyncOpenAI(api_key=settings.openai_api_key))
    if preferred == "anthropic" and settings.anthropic_api_key:
        from anthropic import AsyncAnthropic
        return ("anthropic", AsyncAnthropic(api_key=settings.anthropic_api_key))

    # Fallback: if preferred provider is not configured, use any available key.
    if settings.openai_api_key:
        from openai import AsyncOpenAI
        return ("openai", AsyncOpenAI(api_key=settings.openai_api_key))
    if settings.anthropic_api_key:
        from anthropic import AsyncAnthropic
        return ("anthropic", AsyncAnthropic(api_key=settings.anthropic_api_key))

    return (None, None)


async def _call_llm(prompt: str, max_tokens: int = 500) -> str:
    provider, client = _get_llm_client()
    if client is None:
        logger.warning("No LLM client available — returning empty string")
        return ""

    try:
        if provider == "openai":
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0,
            )
            return resp.choices[0].message.content.strip()
        else:  # anthropic
            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return ""


async def normalize_carrier_name(incoming_name: str, known_carriers: list[dict]) -> str | None:
    """
    Fuzzy-match an incoming carrier name against known carriers.
    Returns carrier_id if a confident match is found, else None.
    """
    if not known_carriers:
        return None

    carrier_list = "\n".join(f"- id={c['id']}, name={c['name']}" for c in known_carriers)
    prompt = f"""You are matching a carrier name from a freight bill to a known carrier in our system.
Incoming carrier name: "{incoming_name}"
Known carriers:
{carrier_list}

If the incoming name clearly refers to one of the known carriers (allowing for abbreviations,
alternate names, or minor variations), reply with ONLY the carrier id (e.g. "CAR001").
If no match is confident, reply with "NO_MATCH".
Reply with nothing else."""

    result = await _call_llm(prompt, max_tokens=20)
    result = result.strip().strip('"')
    if result and result != "NO_MATCH" and result.startswith("CAR"):
        return result
    return None


async def resolve_ambiguous_contract(
    bill: dict,
    candidate_contracts: list[dict],
) -> tuple[dict | None, str]:
    """
    When multiple contracts cover the same lane and date, ask the LLM to
    pick the best one given the bill details. Returns (chosen_contract, reasoning).
    """
    if len(candidate_contracts) == 1:
        return candidate_contracts[0], "Single contract — no ambiguity"

    candidates_json = json.dumps([{
        "id": c["id"],
        "effective_date": c["effective_date"],
        "expiry_date": c["expiry_date"],
        "status": c["status"],
        "notes": c.get("notes", ""),
        "matched_rate_row": c.get("matched_rate_row", {}),
    } for c in candidate_contracts], indent=2)

    bill_summary = json.dumps({
        "bill_date": bill.get("bill_date"),
        "lane": bill.get("lane"),
        "rate_per_kg": bill.get("rate_per_kg"),
        "billed_weight_kg": bill.get("billed_weight_kg"),
    }, indent=2)

    prompt = f"""A freight bill has been submitted and multiple carrier contracts cover the same lane.
Freight bill details:
{bill_summary}

Candidate contracts (all active on the bill date):
{candidates_json}

Choose the SINGLE best matching contract based on:
1. Which contract's rate_per_kg matches the billed rate most closely
2. Contract notes about SLA or shipment type
3. Effective/expiry dates (prefer most recent if rates match)

Reply with a JSON object ONLY (no markdown):
{{"chosen_contract_id": "<id>", "reasoning": "<1-2 sentence explanation>"}}"""

    result = await _call_llm(prompt, max_tokens=200)
    try:
        result = result.strip().lstrip("```json").rstrip("```").strip()
        parsed = json.loads(result)
        chosen_id = parsed.get("chosen_contract_id")
        reasoning = parsed.get("reasoning", "LLM resolved ambiguity")
        chosen = next((c for c in candidate_contracts if c["id"] == chosen_id), None)
        return chosen, reasoning
    except Exception as e:
        logger.error(f"Contract resolution parse failed: {e}. Raw: {result}")
        # Fall back to closest rate match
        bill_rate = bill.get("rate_per_kg", 0)
        best = min(
            candidate_contracts,
            key=lambda c: abs((c.get("matched_rate_row") or {}).get("rate_per_kg", 999) - bill_rate),
        )
        return best, "Fallback: chose contract with closest rate (LLM parse failed)"


async def generate_explanation(
    bill_id: str,
    findings: list[dict],
    decision: str,
    confidence: float,
) -> str:
    """Generate a plain-English explanation of the agent's decision."""
    findings_text = "\n".join(
        f"- [{f['severity'].upper()}] {f['message']}" for f in findings
    )
    prompt = f"""You are summarizing the result of an automated freight bill audit for a logistics ops team.

Freight bill: {bill_id}
Decision: {decision}
Confidence: {confidence:.0%}

Validation findings:
{findings_text}

Write a clear 2-3 sentence explanation suitable for a human reviewer. Be specific about what was checked and what the key issue is (if any). Do not use bullet points."""

    result = await _call_llm(prompt, max_tokens=200)
    if not result:
        errors = [f for f in findings if f.get("severity") == "error"]
        if errors:
            return f"Freight bill {bill_id} flagged with {len(errors)} error(s): {errors[0]['message']}."
        return f"Freight bill {bill_id} processed with decision '{decision}' at {confidence:.0%} confidence."
    return result
