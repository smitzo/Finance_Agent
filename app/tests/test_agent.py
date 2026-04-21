"""
Tests for core agent decision logic.
Focuses on the deterministic rules and confidence scoring — no DB or LLM needed.
Run with: pytest app/tests/test_agent.py -v
"""

import pytest
from app.agent.rules import (
    ValidationResult, Finding,
    check_duplicate, check_carrier_known, check_contract_active,
    check_rate, check_fuel_surcharge, check_base_charge,
    check_weight_vs_bol, check_total_amount,
    compute_confidence,
)


# ── check_duplicate ───────────────────────────────────────────────────────────

def test_no_duplicate():
    f = check_duplicate("SFX/2025/00234", "CAR001", [])
    assert f.severity == "ok"


def test_duplicate_detected():
    f = check_duplicate("SFX/2025/00234", "CAR001", ["FB-2025-101"])
    assert f.severity == "error"
    assert f.code == "DUPLICATE_BILL"


# ── check_carrier_known ───────────────────────────────────────────────────────

def test_carrier_known():
    f = check_carrier_known("CAR001", "Safexpress Logistics")
    assert f.severity == "ok"


def test_carrier_unknown():
    f = check_carrier_known(None, "Gati KWE Logistics")
    assert f.severity == "error"
    assert f.code == "UNKNOWN_CARRIER"


# ── check_contract_active ─────────────────────────────────────────────────────

def test_contract_active():
    contract = {
        "id": "CC-2024-SFX-001",
        "status": "active",
        "effective_date": "2024-01-01",
        "expiry_date": "2025-12-31",
    }
    f = check_contract_active(contract, "2025-02-15")
    assert f.severity == "ok"


def test_contract_expired_status():
    contract = {
        "id": "CC-2023-TCI-001",
        "status": "expired",
        "effective_date": "2023-07-01",
        "expiry_date": "2024-06-30",
    }
    f = check_contract_active(contract, "2025-03-20")
    assert f.severity == "error"
    assert f.code == "CONTRACT_EXPIRED"


def test_contract_date_lapsed():
    contract = {
        "id": "CC-2024-DEL-001",
        "status": "active",
        "effective_date": "2024-04-01",
        "expiry_date": "2025-03-31",
    }
    f = check_contract_active(contract, "2025-04-15")
    assert f.severity == "error"
    assert f.code == "CONTRACT_DATE_LAPSED"


def test_no_contract():
    f = check_contract_active(None, "2025-01-01")
    assert f.severity == "error"
    assert f.code == "NO_CONTRACT"


# ── check_rate ────────────────────────────────────────────────────────────────

def test_rate_exact_match():
    bill = {"rate_per_kg": 15.00}
    rate_row = {"rate_per_kg": 15.00}
    f = check_rate(bill, rate_row, "2025-02-15")
    assert f.severity == "ok"


def test_rate_within_tolerance():
    bill = {"rate_per_kg": 15.10}
    rate_row = {"rate_per_kg": 15.00}
    f = check_rate(bill, rate_row, "2025-02-15")
    assert f.severity == "ok"


def test_rate_mismatch_error():
    # FB-2025-105: 8.70 vs 8.00 = 8.75% over → error (>5%)
    bill = {"rate_per_kg": 8.70}
    rate_row = {"rate_per_kg": 8.00}
    f = check_rate(bill, rate_row, "2025-01-25")
    assert f.severity == "error"
    assert f.code == "RATE_MISMATCH"
    assert f.detail["pct_diff"] == pytest.approx(8.75, rel=1e-2)


# ── check_fuel_surcharge ──────────────────────────────────────────────────────

def test_fuel_surcharge_original():
    bill = {"base_charge": 12750.00, "fuel_surcharge": 1020.00}
    rate_row = {"fuel_surcharge_percent": 8}
    f = check_fuel_surcharge(bill, rate_row, "2025-02-15")
    assert f.severity == "ok"


def test_fuel_surcharge_revised():
    # FB-2025-108: revised on 2024-10-01 to 18%; bill date 2024-11-20
    bill = {"base_charge": 21250.00, "fuel_surcharge": 3825.00}
    rate_row = {
        "fuel_surcharge_percent": 12,
        "revised_on": "2024-10-01",
        "revised_fuel_surcharge_percent": 18,
    }
    f = check_fuel_surcharge(bill, rate_row, "2024-11-20")
    assert f.severity == "ok"


def test_fuel_surcharge_wrong_rate_used():
    bill = {"base_charge": 21250.00, "fuel_surcharge": 2550.00}  # 12% instead of 18%
    rate_row = {
        "fuel_surcharge_percent": 12,
        "revised_on": "2024-10-01",
        "revised_fuel_surcharge_percent": 18,
    }
    f = check_fuel_surcharge(bill, rate_row, "2024-11-20")
    assert f.severity == "error"


# ── check_weight_vs_bol ───────────────────────────────────────────────────────

def test_weight_clean_match():
    bill = {"billed_weight_kg": 850}
    bols = [{"actual_weight_kg": 850}]
    f = check_weight_vs_bol(bill, bols, 0)
    assert f.severity == "ok"


def test_weight_partial_delivery_valid():
    bill = {"billed_weight_kg": 800}
    bols = [{"actual_weight_kg": 1200}]
    f = check_weight_vs_bol(bill, bols, 0)
    assert f.severity in ("ok", "warn")


def test_weight_overbilling_detected():
    # FB-2025-104: 1500kg billed, BOL=1200kg, prior billed=800kg → remaining=400kg
    bill = {"billed_weight_kg": 1500}
    bols = [{"actual_weight_kg": 1200}]
    f = check_weight_vs_bol(bill, bols, prior_billed_weight=800)
    assert f.severity == "error"
    assert f.code == "WEIGHT_MISMATCH"


# ── check_total_amount ────────────────────────────────────────────────────────

def test_total_consistent():
    bill = {"base_charge": 12750.00, "fuel_surcharge": 1020.00, "gst_amount": 2479.00, "total_amount": 16249.00}
    f = check_total_amount(bill)
    assert f.severity == "ok"


def test_total_inconsistent():
    bill = {"base_charge": 12750.00, "fuel_surcharge": 1020.00, "gst_amount": 2479.00, "total_amount": 99999.00}
    f = check_total_amount(bill)
    assert f.severity == "error"


# ── confidence scoring ────────────────────────────────────────────────────────

def test_confidence_all_ok():
    vr = ValidationResult()
    vr.add(Finding("A", "ok", "good"))
    vr.add(Finding("B", "ok", "good"))
    assert compute_confidence(vr) == 1.0


def test_confidence_one_error():
    vr = ValidationResult()
    vr.add(Finding("A", "error", "bad"))
    assert compute_confidence(vr) == pytest.approx(0.75, abs=0.01)


def test_confidence_floored():
    vr = ValidationResult()
    for i in range(10):
        vr.add(Finding(f"E{i}", "error", "bad"))
    assert compute_confidence(vr) == 0.0


def test_confidence_mixed():
    vr = ValidationResult()
    vr.add(Finding("A", "error", "bad"))   # -0.25
    vr.add(Finding("B", "warn", "meh"))    # -0.08
    vr.add(Finding("C", "ok", "good"))
    expected = round(1.0 - 0.25 - 0.08, 3)
    assert compute_confidence(vr) == pytest.approx(expected, abs=0.001)