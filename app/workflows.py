"""Supported invoice workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass


FREIGHT_AUDIT = "freight_audit"


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    description: str
    agent: str


SUPPORTED_WORKFLOWS: dict[str, WorkflowDefinition] = {
    FREIGHT_AUDIT: WorkflowDefinition(
        name=FREIGHT_AUDIT,
        description="Audit freight bills against carrier contracts, shipments, and BOLs.",
        agent="freight_bill_langgraph",
    ),
}


def is_supported_workflow(workflow_type: str) -> bool:
    return workflow_type in SUPPORTED_WORKFLOWS
