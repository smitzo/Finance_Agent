# Functional and Technical Flows

## Functional flow

```mermaid
flowchart TD
    A[Bill arrives] --> B[Validate required fields]
    B --> C{Previously accepted?}
    C -->|Same idempotency key| D[Return existing bill]
    C -->|Duplicate invoice| E[Reject intake with conflict]
    C -->|New bill| F[Queue audit]
    F --> G[Join carrier, contract, shipment and BOL evidence]
    G --> H[Run exact audit rules]
    H --> I{Ambiguous context?}
    I -->|Yes, safe to continue| J[Bounded AI resolution or deterministic fallback]
    I -->|No| K[Score and decide]
    J --> K
    K -->|Approve, dispute, reject| L[Persist final decision]
    K -->|Flag| M[Pause in review queue]
    M --> N[Reviewer decides]
    N --> L
    L --> O[Metrics, evidence and audit trail available]
```

### Operator journey

1. Sign in to a tenant workspace.
2. Create a bill manually, submit a JSON batch, or load the synthetic demo.
3. Monitor pending and processing bills while workers audit them.
4. Open a bill to inspect its findings, evidence, confidence, explanation, and audit timeline.
5. Work the review queue for paused cases.
6. Submit `approve`, `dispute`, or `reject` with notes.
7. Confirm the resumed bill reaches a final state.

## Technical intake flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Queue as Redis/Celery
    participant Worker

    Client->>API: POST /freight-bills + Basic auth + X-Tenant-ID
    API->>API: authenticate, validate, bind correlation ID
    API->>DB: check ID, idempotency key, duplicate
    API->>DB: insert bill + bill_ingested audit event
    DB-->>API: commit
    API->>Queue: enqueue process_bill
    API->>DB: persist Celery task ID
    API-->>Client: 202 Accepted + X-Correlation-ID
    Queue-->>Worker: deliver task
```

For bulk intake, each accepted item is committed through the same service logic and then enqueued independently. Invalid or duplicate items are reported without discarding unrelated accepted items.

## Technical agent flow

```mermaid
sequenceDiagram
    participant Worker
    participant DB as PostgreSQL
    participant Graph as Neo4j
    participant LG as LangGraph
    participant Model as LLM provider

    Worker->>DB: mark processing and store thread/task IDs
    Worker->>Graph: add current bill node
    Worker->>LG: start durable thread
    LG->>Graph: load carrier/contracts/shipment/BOL/prior bills
    LG->>LG: run deterministic rules
    alt hard deterministic blocker
        LG->>LG: skip model calls
    else fuzzy name or overlapping contracts
        LG->>Model: bounded prompt
        Model-->>LG: carrier/contract choice
        LG->>LG: deterministic fallback if unavailable/invalid
    end
    LG->>LG: compute confidence and decision
    LG->>DB: persist result, evidence, and audit events
```

## Human-review resume flow

```mermaid
sequenceDiagram
    participant Agent as LangGraph
    participant CP as PostgreSQL checkpoint
    participant UI
    participant API
    participant Queue as Celery

    Agent->>CP: interrupt and persist state
    UI->>API: GET /review-queue
    API-->>UI: awaiting_review bills
    UI->>API: POST /review/{id}
    API->>API: verify tenant, status, thread ID
    API->>Queue: enqueue resume_bill
    Queue->>Agent: update human_review state
    Agent->>CP: resume same thread
    Agent->>API: no synchronous callback
    Agent->>CP: persist final checkpoint
```

The worker also writes the final business result to normal PostgreSQL tables. A checkpoint alone is not considered a completed product decision.

## Demo load flow

1. `POST /admin/demo/load` removes only demo-prefixed records for the current tenant.
2. It inserts synthetic company, partner, carrier, contract, shipment, BOL, bill, and audit records.
3. Each bill stores its demo category, scenario, and expected behavior in `evidence`.
4. The API rebuilds the tenant graph once.
5. All 120 bills are queued through the same Celery path as normal bills.
6. `DELETE /admin/demo` removes only the synthetic portfolio and rebuilds the tenant graph.

## Failure flow

- Validation failures return an HTTP error before persistence.
- Duplicate/idempotent behavior is resolved before queueing.
- Connection and timeout task failures retry with backoff up to three times.
- Unhandled agent errors move the bill to `awaiting_review`, add an `agent_error` audit event, and retain the exception message for operators.
- Provider quota/rate-limit failures open a process-local circuit breaker; deterministic processing continues.
- Health endpoints isolate API, database, and graph reachability.
