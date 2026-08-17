# Project Overview

## Purpose

FreightFlow AI is a multi-tenant freight-bill audit control tower. It checks carrier invoices against contractual rates, shipment records, and bills of lading (BOLs), then produces an auditable decision or pauses the workflow for human review.

The system is designed around a simple control principle: exact financial facts are evaluated by deterministic code; language models are limited to fuzzy or ambiguous inputs.

## The problem it solves

Freight invoices commonly contain:

- repeated invoice numbers;
- incorrect rates, minimum charges, or fuel surcharges;
- billed weight unsupported by delivery evidence;
- expired, future, missing, or overlapping contracts;
- inconsistent totals;
- carrier names that differ from the master-data spelling;
- cases where policy requires a responsible person to make the final decision.

Manually joining all of this evidence is slow. Fully delegating it to an LLM would make exact arithmetic and policy enforcement non-deterministic. FreightFlow combines a transactional system, relationship traversal, deterministic checks, bounded AI assistance, and durable review.

## Current product capabilities

- Single and bulk JSON bill intake.
- Tenant-scoped authentication and data access.
- Retry-safe intake through an optional idempotency key.
- Deterministic duplicate, carrier, contract, rate, surcharge, base-charge, weight, UOM, and total checks.
- Neo4j traversal of carrier, contract, lane, shipment, BOL, and prior-bill relationships.
- LLM-assisted carrier normalization, overlapping-contract selection, and readable explanations.
- Celery-backed asynchronous processing with Redis queueing.
- PostgreSQL-backed LangGraph checkpoints for durable human review.
- Review queue with approve, dispute, and reject actions.
- Evidence snapshots, append-only audit events, correlation-aware JSON logs, metrics, and health probes.
- React operations UI for overview, bills, review, analytics, company, and partner management.
- A synthetic 120-bill demo portfolio covering normal, ambiguous, and edge behavior.

## Decision model

Each unique finding is classified as `ok`, `warn`, or `error`.

```text
confidence = 1.00 - (0.25 x errors) - (0.08 x warnings)
confidence = clamp(confidence, 0.00, 1.00)
overlapping-contract ambiguity = additional 0.15 deduction
```

The default policy is:

| Condition | Agent decision | Runtime behavior |
|---|---|---|
| Duplicate bill | `reject` | Finalize immediately |
| Confidence at least `0.85` and no errors | `auto_approve` | Finalize immediately |
| Confidence at most `0.40`, or hard carrier/weight error | `dispute` | Finalize immediately |
| Anything else | `flag` | Checkpoint and wait for human review |

Thresholds are configurable. Changing them is a business-policy change and should be validated against labelled historical outcomes.

## System boundaries

PostgreSQL is the source of truth for business and workflow state. Neo4j is a derived traversal store. Redis transports work but is not the workflow record. LangGraph checkpoints are durable execution state, not a replacement for the product tables.

The current `admin/admin` bootstrap and tenant-scoped `demo/demo` login are local/demo controls. They are not an internet-facing identity solution. See [Improvement and scaling roadmap](improvements.md).

## Success criteria

The product is working correctly when:

- a bill cannot read or mutate another tenant's records;
- exact checks produce repeatable findings for the same evidence;
- API restarts do not cancel queued work;
- worker restarts do not lose a paused review;
- a reviewer resumes the same workflow thread;
- every decision can be reconstructed from persisted evidence, audit events, and correlation-aware logs;
- demo cleanup removes only synthetic demo records.
