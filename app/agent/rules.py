"""
Deterministic Validation Rules
================================
All charge, weight, date, and rate validations are done here — no LLM.
Returns structured findings that feed into the confidence score.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any


TOLERANCE = 0.02  # 2% tolerance on monetary amounts


@dataclass
class Finding:
    code: str
    severity: str          # "ok" | "warn" | "error"
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "warn"]

    @property
    def oks(self):
        return [f for f in self.findings if f.severity == "ok"]

    def add(self, finding: Finding):
        self.findings.append(finding)


# Helpers 

def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _within_tolerance(actual: float, expected: float) -> bool:
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= TOLERANCE


# Individual checks 

def check_duplicate(bill_number: str, carrier_id: str, existing_bill_ids: list[str]) -> Finding:
    if existing_bill_ids:
        return Finding(
            code="DUPLICATE_BILL",
            severity="error",
            message=f"Bill number {bill_number} already exists (IDs: {existing_bill_ids})",
            detail={"existing": existing_bill_ids},
        )
    return Finding(code="NO_DUPLICATE", severity="ok", message="No duplicate found")


def check_carrier_known(carrier_id: str | None, carrier_name: str) -> Finding:
    if not carrier_id:
        return Finding(
            code="UNKNOWN_CARRIER",
            severity="error",
            message=f"Carrier '{carrier_name}' has no record in the system",
        )
    return Finding(code="CARRIER_KNOWN", severity="ok", message=f"Carrier {carrier_id} found")


def check_contract_active(contract: dict | None, bill_date: str) -> Finding:
    if not contract:
        return Finding(
            code="NO_CONTRACT",
            severity="error",
            message="No matching contract found for carrier + lane",
        )
    bd = _parse_date(bill_date)
    eff = _parse_date(contract.get("effective_date", ""))
    exp = _parse_date(contract.get("expiry_date", ""))

    if contract.get("status") == "expired":
        return Finding(
            code="CONTRACT_EXPIRED",
            severity="error",
            message=f"Contract {contract['id']} is marked expired",
            detail={"contract_id": contract["id"]},
        )
    if bd and exp and bd > exp:
        return Finding(
            code="CONTRACT_DATE_LAPSED",
            severity="error",
            message=f"Bill date {bill_date} is after contract expiry {contract['expiry_date']}",
            detail={"contract_id": contract["id"], "expiry": contract["expiry_date"]},
        )
    if bd and eff and bd < eff:
        return Finding(
            code="CONTRACT_NOT_YET_ACTIVE",
            severity="error",
            message=f"Bill date {bill_date} is before contract effective date {contract['effective_date']}",
            detail={"contract_id": contract["id"]},
        )
    return Finding(
        code="CONTRACT_ACTIVE",
        severity="ok",
        message=f"Contract {contract['id']} is active on bill date",
    )


def check_rate(bill: dict, rate_row: dict, bill_date: str) -> Finding:
    """Compare billed rate_per_kg against the contracted rate."""
    contracted_rate = rate_row.get("rate_per_kg") or rate_row.get("alternate_rate_per_kg")
    if contracted_rate is None:
        return Finding(
            code="RATE_UNKNOWN",
            severity="warn",
            message="Cannot determine per-kg rate from contract (FTL contract, see UOM check)",
        )

    billed_rate = bill.get("rate_per_kg", 0)
    if _within_tolerance(billed_rate, contracted_rate):
        return Finding(
            code="RATE_MATCH",
            severity="ok",
            message=f"Rate ₹{billed_rate}/kg matches contracted ₹{contracted_rate}/kg",
        )
    pct = ((billed_rate - contracted_rate) / contracted_rate) * 100
    severity = "error" if abs(pct) > 5 else "warn"
    return Finding(
        code="RATE_MISMATCH",
        severity=severity,
        message=f"Billed ₹{billed_rate}/kg vs contracted ₹{contracted_rate}/kg ({pct:+.1f}%)",
        detail={"billed": billed_rate, "contracted": contracted_rate, "pct_diff": round(pct, 2)},
    )


def check_fuel_surcharge(bill: dict, rate_row: dict, bill_date: str) -> Finding:
    """Check fuel surcharge — handles mid-term revisions."""
    base = bill.get("base_charge", 0)
    billed_fsc = bill.get("fuel_surcharge", 0)

    revised_on = rate_row.get("revised_on")
    bd = _parse_date(bill_date)
    rev_date = _parse_date(revised_on) if revised_on else None

    if rev_date and bd and bd >= rev_date:
        fsc_pct = rate_row.get("revised_fuel_surcharge_percent", rate_row.get("fuel_surcharge_percent", 0))
        source = "revised"
    else:
        fsc_pct = rate_row.get("fuel_surcharge_percent", 0)
        source = "original"

    expected_fsc = round(base * fsc_pct / 100, 2)
    if _within_tolerance(billed_fsc, expected_fsc):
        return Finding(
            code="FSC_MATCH",
            severity="ok",
            message=f"Fuel surcharge ₹{billed_fsc} matches {fsc_pct}% ({source})",
        )
    return Finding(
        code="FSC_MISMATCH",
        severity="error",
        message=f"Fuel surcharge ₹{billed_fsc} ≠ expected ₹{expected_fsc} ({fsc_pct}% {source})",
        detail={"billed_fsc": billed_fsc, "expected_fsc": expected_fsc, "pct": fsc_pct, "source": source},
    )


def check_base_charge(bill: dict, rate_row: dict) -> Finding:
    """Check base_charge = weight × rate, respecting min_charge."""
    weight = bill.get("billed_weight_kg", 0)
    rate = rate_row.get("rate_per_kg") or rate_row.get("alternate_rate_per_kg")
    if rate is None:
        ftl_rate = rate_row.get("rate_per_unit")
        if ftl_rate:
            min_charge = rate_row.get("min_charge", 0)
            expected = max(ftl_rate, min_charge)
            billed = bill.get("base_charge", 0)
            if _within_tolerance(billed, expected):
                return Finding(
                    code="BASE_CHARGE_MATCH",
                    severity="ok",
                    message=f"FTL base charge ₹{billed} matches ₹{expected}",
                )
            return Finding(
                code="BASE_CHARGE_MISMATCH",
                severity="error",
                message=f"FTL base charge ₹{billed} ≠ expected ₹{expected}",
                detail={"billed": billed, "expected": expected},
            )
        return Finding(
            code="BASE_CHARGE_UNKNOWN",
            severity="warn",
            message="Cannot validate base charge — no rate available",
        )

    expected_raw = weight * rate
    min_charge = rate_row.get("min_charge", 0)
    expected = max(expected_raw, min_charge)
    billed = bill.get("base_charge", 0)

    if _within_tolerance(billed, expected):
        return Finding(
            code="BASE_CHARGE_MATCH",
            severity="ok",
            message=f"Base charge ₹{billed} correct (weight={weight}kg × ₹{rate})",
        )
    return Finding(
        code="BASE_CHARGE_MISMATCH",
        severity="error",
        message=f"Base charge ₹{billed} ≠ expected ₹{expected} (weight={weight}kg × ₹{rate}, min=₹{min_charge})",
        detail={"billed": billed, "expected": round(expected, 2), "weight": weight, "rate": rate},
    )


def check_weight_vs_bol(
    bill: dict,
    bols: list[dict],
    prior_billed_weight: float = 0,
    **kwargs,
) -> Finding:
    """
    Check billed weight against BOL actual weight.
    For partial deliveries, accounts for weight already covered by prior bills.
    """
    if "previously_billed_weight" in kwargs and not prior_billed_weight:
        prior_billed_weight = kwargs["previously_billed_weight"]

    billed_weight = bill.get("billed_weight_kg", 0)
    bol_total = sum(b.get("actual_weight_kg", 0) for b in bols)

    if not bols:
        return Finding(code="NO_BOL", severity="warn", message="No BOL found to validate weight")

    remaining = bol_total - prior_billed_weight
    if remaining < 0:
        remaining = 0

    if _within_tolerance(billed_weight, remaining) or _within_tolerance(billed_weight, bol_total):
        return Finding(
            code="WEIGHT_MATCH",
            severity="ok",
            message=f"Billed {billed_weight}kg consistent with BOL {bol_total}kg (prior billed: {prior_billed_weight}kg)",
        )

    over = billed_weight - remaining
    severity = "error" if over > 0 else "warn"
    return Finding(
        code="WEIGHT_MISMATCH",
        severity=severity,
        message=f"Billed {billed_weight}kg vs BOL remaining {remaining}kg (BOL total={bol_total}kg, prior billed={prior_billed_weight}kg)",
        detail={
            "billed_weight": billed_weight,
            "bol_total": bol_total,
            "prior_billed": prior_billed_weight,
            "remaining": remaining,
            "over_by": round(over, 2),
        },
    )


def check_uom_mismatch(bill: dict, rate_row: dict) -> Finding:
    """Detect unit-of-measure differences (per-kg bill vs FTL contract)."""
    billing_unit = bill.get("billing_unit", "kg")
    contract_unit = rate_row.get("unit", "kg")
    alt_rate = rate_row.get("alternate_rate_per_kg")

    if contract_unit == "FTL" and billing_unit == "kg":
        if alt_rate:
            return Finding(
                code="UOM_ALT_BILLING",
                severity="ok",
                message=f"Contract is FTL but alternate per-kg rate (₹{alt_rate}/kg) applies — semantically valid",
                detail={"contract_unit": contract_unit, "bill_unit": billing_unit},
            )
        return Finding(
            code="UOM_MISMATCH",
            severity="warn",
            message="Contract unit is FTL but bill is per-kg with no alternate rate",
            detail={"contract_unit": contract_unit, "bill_unit": billing_unit},
        )
    return Finding(code="UOM_MATCH", severity="ok", message=f"Billing unit consistent ({billing_unit})")


def check_total_amount(bill: dict) -> Finding:
    """Verify total = base + fsc + gst (internal consistency)."""
    base = bill.get("base_charge", 0)
    fsc = bill.get("fuel_surcharge", 0)
    gst = bill.get("gst_amount", 0)
    total = bill.get("total_amount", 0)
    expected = round(base + fsc + gst, 2)
    if _within_tolerance(total, expected):
        return Finding(
            code="TOTAL_CONSISTENT",
            severity="ok",
            message=f"Total ₹{total} is internally consistent",
        )
    return Finding(
        code="TOTAL_INCONSISTENT",
        severity="error",
        message=f"Total ₹{total} ≠ base+fsc+gst = ₹{expected}",
        detail={"total": total, "expected": expected},
    )


# ── Confidence score ──────────────────────────────────────────────────────────

def compute_confidence(result: ValidationResult) -> float:
    """
    Score from 0.0 to 1.0 based on findings.
    - Start at 1.0
    - Each error deducts 0.25 (floored at 0)
    - Each warning deducts 0.08
    - Ambiguous contract (multiple candidates) deducts 0.15 separately (applied in decide node)
    """
    score = 1.0
    for f in result.findings:
        if f.severity == "error":
            score -= 0.25
        elif f.severity == "warn":
            score -= 0.08
    return round(max(0.0, min(1.0, score)), 3)
