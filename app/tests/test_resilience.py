"""
Resilience tests for high-volume scoring and LLM failure handling.
Run with: pytest app/tests/test_resilience.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent import llm_service
from app.agent.rules import Finding, ValidationResult, compute_confidence


def test_confidence_scoring_stays_bounded_for_large_batches() -> None:
    """
    Simulate many invoice evaluations quickly and assert score stability.
    This guards against crashes/invalid values during bulk processing.
    """
    scores: list[float] = []
    for i in range(1000):
        vr = ValidationResult()
        # Deterministic spread of severities to mimic diverse invoice quality.
        if i % 7 == 0:
            vr.add(Finding(code="E1", severity="error", message="Hard mismatch"))
        if i % 3 == 0:
            vr.add(Finding(code="W1", severity="warn", message="Missing context"))
        vr.add(Finding(code="OK", severity="ok", message="Basic checks passed"))
        scores.append(compute_confidence(vr))

    assert len(scores) == 1000
    assert all(0.0 <= score <= 1.0 for score in scores)
    # Ensure we exercised variety, not a single flat outcome.
    assert len(set(scores)) >= 3


@pytest.mark.asyncio
async def test_llm_quota_error_opens_circuit_and_prevents_call_storm(monkeypatch) -> None:
    """
    First quota-like failure should open the circuit.
    Subsequent calls should be skipped immediately, avoiding repeated paid API attempts.
    """
    calls = {"count": 0}

    async def _quota_failure(**_kwargs):
        calls["count"] += 1
        raise RuntimeError("429 insufficient_quota")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_quota_failure),
        )
    )

    monkeypatch.setattr(llm_service, "_llm_circuit_open_until_monotonic", 0.0)
    monkeypatch.setattr(llm_service.settings, "llm_circuit_breaker_cooldown_seconds", 120, raising=False)
    monkeypatch.setattr(llm_service, "_get_llm_client", lambda: ("openai", fake_client))

    first = await llm_service._call_llm("first prompt", operation="quota_test_first")
    second = await llm_service._call_llm("second prompt", operation="quota_test_second")

    assert first == ""
    assert second == ""
    # Only one outbound API attempt; second call skipped by circuit breaker.
    assert calls["count"] == 1
    assert llm_service._is_llm_circuit_open() is True


@pytest.mark.asyncio
async def test_llm_circuit_allows_recovery_after_cooldown(monkeypatch) -> None:
    """
    Once cooldown passes, LLM calls should resume normally.
    """
    async def _success(**_kwargs):
        return SimpleNamespace(
            id="resp_1",
            model="gpt-4o-mini",
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="Recovered response"))],
        )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=_success),
        )
    )

    # Force-circuit to appear expired before this call.
    monkeypatch.setattr(llm_service, "_llm_circuit_open_until_monotonic", 0.0)
    monkeypatch.setattr(llm_service, "_get_llm_client", lambda: ("openai", fake_client))

    result = await llm_service._call_llm("resume prompt", operation="recovery_test")
    assert result == "Recovered response"
