# Finance Agent Architecture Understanding

## 1. What This System Does

This backend processes invoice-like workflows, starting with freight bill audits.
An invoice is accepted through the API, stored in Postgres, enriched with graph
context from carriers, contracts, shipments, and bills of lading, then evaluated
by a LangGraph agent.

The agent combines two types of intelligence:

1. Deterministic rules for facts that must be exact, such as totals, rates,
   weight checks, duplicate bills, and contract dates.
2. LLM reasoning for fuzzy decisions, such as matching an imperfect carrier
   name or choosing between overlapping contracts.

The important production principle is that the LLM does not perform accounting
math. It only helps with ambiguous text or business-context choices. Verifiable
checks stay in normal Python rules.

## 2. High-Level Request Flow

1. A client sends `POST /freight-bills` with `X-Tenant-ID`.
2. The API validates the payload and stores a `FreightBill` row in Postgres.
3. The graph service ensures that tenant's graph context is warm.
4. The API queues the agent in the background.
5. The agent loads carrier, contract, shipment, BOL, and prior-bill context.
6. Deterministic checks run first.
7. If contract selection is ambiguous and no hard deterministic blocker exists,
   the LLM can choose the best contract.
8. The agent computes confidence and returns one of:
   - `auto_approve`
   - `flag`
   - `dispute`
   - `reject`
9. Low-confidence `flag` cases pause for human review.
10. The result, confidence, evidence, and audit events are persisted.

## 3. Why Multi-Tenancy Matters

Multi-tenancy means the same backend can serve multiple customers or business
units without mixing their data.

This project now uses `tenant_id` on core tables:

- `carriers`
- `carrier_contracts`
- `shipments`
- `bills_of_lading`
- `freight_bills`
- `audit_logs`

Every API request can specify the tenant with:

```http
X-Tenant-ID: acme
```

If the header is missing, the app uses `DEFAULT_TENANT_ID`, which defaults to
`default`.

The service layer enforces tenant scope. This is important because route-level
checks are not enough. A future route could forget a filter; the service
functions make tenant filtering the normal path.

## 4. Workflow Types

The system now has a `workflow_type` column on `freight_bills`.

Current default:

```text
freight_audit
```

This creates room for additional invoice workflows later, for example:

- `freight_audit`
- `accessorial_audit`
- `customs_invoice_audit`
- `vendor_invoice_audit`

The current LangGraph path still implements freight audit behavior, but the
data model and API are no longer locked to only one invoice type.

Clients can discover supported workflow types with:

```http
GET /workflows
```

## 5. Why Neo4j Replaces NetworkX

The earlier prototype used NetworkX in memory. That is fine for a small
assignment or demo because it is simple and fast enough for tiny data.

Industry use is different:

- data can grow to millions of nodes and relationships
- multiple API workers may run at once
- graph state must survive restarts
- queries need indexes and stable traversal performance
- operations teams need a real backend to monitor and tune

Neo4j is designed for graph traversal. This makes it a better fit for questions
like:

- Which contracts cover this carrier and lane?
- Which shipment does this invoice reference?
- Which BOLs prove the delivered weight?
- Which prior bills already consumed shipment weight?
- Are there duplicate bills in this tenant?

The production graph model uses labels such as:

- `Carrier`
- `Contract`
- `Lane`
- `Shipment`
- `BOL`
- `FreightBill`

And relationships such as:

- `HAS_CONTRACT`
- `COVERS_LANE`
- `HAS_SHIPMENT`
- `HAS_BOL`
- `REFERENCES`

## 6. Why Postgres Still Exists

Neo4j is not replacing Postgres.

Postgres remains the source of truth for workflow state:

- invoice status
- decisions
- confidence scores
- audit logs
- reviewer decisions
- evidence snapshots
- created and updated timestamps

Neo4j is the traversal store. It is optimized for relationship questions.
Postgres is optimized for durable business records, transactions, reporting,
and migrations.

This split is common in production systems:

```text
Postgres = source of truth and workflow state
Neo4j    = graph traversal and relationship lookup
```

## 7. Graph Backend Abstraction

The code now uses `GraphService` instead of directly using a NetworkX object.

The agent asks for business context through methods such as:

- `list_carriers`
- `get_carrier_node`
- `get_contracts_for_lane`
- `get_shipment_node`
- `get_bols_for_shipment`
- `get_freight_bills_for_shipment`
- `find_duplicate_bill_ids`

This is an important design decision. The agent does not need to know if the
data comes from Neo4j, memory, or a future graph engine.

There are currently two backends:

1. `Neo4jGraphBackend`
   - production backend
   - persistent
   - indexed
   - works across API instances
2. `MemoryGraphBackend`
   - local/test fallback
   - no NetworkX dependency
   - useful when Neo4j is not configured

## 8. Agent Design

The agent is built with LangGraph. Think of LangGraph as a state machine for AI
workflows. Each node receives state, does one job, and returns updated state.

Current nodes:

1. `load_context`
   - reads graph context for the invoice
   - finds carrier, contracts, shipment, BOLs, duplicates, and prior billed weight
2. `validate`
   - runs deterministic checks
3. `resolve_ambiguity`
   - asks the LLM to choose among overlapping contracts only when appropriate
4. `decide`
   - computes confidence and decision
5. `human_review`
   - pauses for human input when needed
6. `finalize`
   - produces final explanation and audit output

The state carries `tenant_id`, so graph traversal and persistence remain scoped
to the correct tenant throughout the agent run.

## 9. AI Boundaries

The LLM is intentionally limited.

Good LLM use:

- fuzzy carrier name matching
- ambiguous contract choice
- plain-English explanation generation

Bad LLM use:

- calculating invoice totals
- deciding if a date is inside a contract term
- checking exact weight mismatches
- detecting duplicate invoice numbers

The system uses deterministic Python rules for exact checks because they are
testable, explainable, and repeatable.

## 10. LLM Resilience

The LLM service includes a circuit breaker.

If the provider returns quota or rate-limit errors, the circuit opens for a
cooldown period. While open, calls are skipped immediately. This prevents a
large invoice batch from hammering the provider and wasting time or money.

The LLM layer now supports both:

- OpenAI
- Anthropic

Model names are configurable:

```env
LLM_OPENAI_MODEL=gpt-4o-mini
LLM_ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

The contract-resolution parser also extracts JSON defensively from fenced LLM
responses, because real model outputs can include markdown even when prompted
not to.

## 11. Bulk Ingestion and Throughput

Single invoice ingest still works.

Bulk ingest now avoids creating one independent background task per invoice.
Accepted invoices are passed to a batch runner, which chunks the work by:

```env
BULK_INGEST_BATCH_SIZE=250
```

Actual concurrent agent execution is still bounded by:

```env
MAX_CONCURRENT_AGENT_RUNS=8
```

This gives two controls:

1. batch size controls queue shape
2. max concurrent runs controls live workload pressure

This is safer for large imports because it avoids uncontrolled task fan-out.

Each invoice can include an `idempotency_key`. This lets clients safely retry a
request after a timeout without creating a duplicate workflow run. The key is
unique within `(tenant_id, workflow_type)`.

## 12. Database Migrations

The project now includes Alembic.

Important files:

- `alembic.ini`
- `migrations/env.py`
- `migrations/versions/0001_tenant_workflow_columns.py`

Why this matters:

`Base.metadata.create_all()` can create missing tables, but it does not safely
modify existing production tables. Alembic gives controlled, reviewable schema
changes.

Container startup now runs:

```bash
alembic upgrade head
```

before seeding and starting the API.

## 13. Key Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://...
DEFAULT_TENANT_ID=default

GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j

LLM_PROVIDER=openai
LLM_OPENAI_MODEL=gpt-4o-mini
LLM_ANTHROPIC_MODEL=claude-3-5-haiku-latest
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

MAX_CONCURRENT_AGENT_RUNS=8
BULK_INGEST_BATCH_SIZE=250
```

## 14. Health Checks

The API exposes:

- `/health`
- `/health/db`
- `/health/graph`

`/health/graph` is important after the Neo4j refactor. It confirms whether the
graph backend is memory or Neo4j and whether it is reachable.

## 15. Important Design Decisions

### Keep deterministic checks outside the LLM

This keeps financial validation auditable and repeatable.

### Use Neo4j for traversal, not as the source of truth

Postgres remains the durable workflow store. Neo4j accelerates relationship
queries.

### Use tenant IDs everywhere

Tenant boundaries must exist in the database, service layer, graph layer, and
agent state. Missing any layer creates data leakage risk.

### Keep a memory graph backend

This is not the production graph, but it makes tests and local development
possible when Neo4j is unavailable.

### Add workflow type early

Even if only freight audit exists today, storing workflow type prevents future
invoice workflows from being bolted on awkwardly.

## 16. What Still Needs Future Work

This refactor creates the production foundation, but more phases are still
needed for full industry-grade scale:

- replace LangGraph `MemorySaver` with a durable checkpointer
- add authentication and tenant authorization, not just tenant headers
- add idempotency keys for bulk ingest
- add pagination to bill listing and audit endpoints
- add structured observability with trace IDs
- add async job queue infrastructure for very large imports
- add contract/reference-data management APIs
- add full Neo4j integration tests with a real test container
- split workflow-specific agent logic behind a workflow registry
- add role-based access control for human review actions

## 17. Beginner Mental Model

If you are new to AI systems, think of this backend like a careful finance
analyst with tools:

- Postgres is the filing cabinet.
- Neo4j is the relationship map pinned on the wall.
- Deterministic rules are the calculator.
- The LLM is the assistant who can interpret messy names or explain a decision.
- LangGraph is the checklist that makes sure each step happens in order.
- Human review is the escalation desk for uncertain cases.

The main rule is simple: use the calculator for math, use the map for
relationships, use the filing cabinet for records, and use the LLM only where
language or ambiguity actually matters.
