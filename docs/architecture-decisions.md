# Architecture Decisions and Alternatives

## Current strategy at a glance

The current implementation is a modular monolith at the code level with separately deployable runtime processes. PostgreSQL owns truth, Neo4j owns traversal, Redis/Celery owns asynchronous delivery, LangGraph owns workflow sequencing/checkpoints, deterministic Python owns exact validation, and an LLM assists only with ambiguity.

This is a deliberate middle ground: production-shaped process boundaries without the operational cost of many independently versioned business microservices.

## Decision summary

| Decision | Current choice | Main reason |
|---|---|---|
| Exact validation | Python rules | Repeatable, testable, explainable |
| Ambiguity | Bounded LLM with fallback | Useful on messy language without delegating accounting |
| Business source of truth | PostgreSQL | Transactions, constraints, migrations, reporting |
| Relationship lookup | Neo4j projection | Natural multi-hop evidence traversal |
| Background execution | Celery + Redis | Work survives API request/process lifetime |
| Workflow state | LangGraph + PostgreSQL saver | Durable interrupt/resume semantics |
| Schema evolution | Alembic | Reviewable, ordered deployment changes |
| Runtime shape | Modular monolith + separate API/worker | Clear ownership with manageable operations |
| Demo | Deterministic synthetic portfolio | Safe, repeatable, comprehensive product exercise |

## Rules plus bounded AI

Chosen approach:

- Python calculates totals, tolerances, dates, charges, and weights.
- The model normalizes fuzzy names, chooses among allowed contracts, and writes explanations.
- Hard deterministic blockers skip model calls.
- Unavailable or malformed model output has a deterministic fallback.

Alternatives:

- **LLM-only audit:** flexible, but arithmetic and policy outcomes can vary and are difficult to prove. Not suitable for the control layer.
- **Rules-only audit:** maximally deterministic, but brittle for name variants, unstructured notes, and overlapping choices. A valid option for deployments that forbid external models; the current fallback path already supports degraded operation.
- **Classical similarity model:** embeddings or edit-distance matching can replace carrier-name LLM calls at lower cost. This is attractive once labelled aliases exist.

## PostgreSQL plus Neo4j

Chosen approach: retain normalized transactional state in PostgreSQL and project relationship data to Neo4j.

Alternatives:

- **PostgreSQL only:** recursive CTEs and indexed join tables reduce infrastructure. This may be the better choice until traversals become deep or highly connected. It also avoids dual-write/projection freshness concerns.
- **Neo4j only:** simplifies the number of stores but weakens conventional transaction/reporting/migration workflows for this product.
- **Event-sourced projection:** publish committed changes and build Neo4j asynchronously. This is the strongest long-term consistency model but adds a broker, consumers, replay, and lag monitoring.

Current limitation: graph refresh is imperative and not backed by a durable projection event stream. PostgreSQL remains authoritative whenever stores disagree.

## Celery rather than request background tasks

FastAPI background tasks are simple but disappear with an API process and compete with request capacity. Celery provides independent scaling, late acknowledgement, retry controls, and operational queue visibility.

Alternatives include Dramatiq/RQ for a smaller surface, or Kafka/Temporal for higher-throughput event processing and stronger workflow orchestration. Temporal could replace both Celery and LangGraph durability, but would be a significant architectural rewrite and offers less native graph/LLM state-machine ergonomics.

## PostgreSQL checkpoints

In-memory checkpointing is useful in tests but loses human-review state on restart. `AsyncPostgresSaver` keeps workflow threads next to the existing durable database boundary. A separate workflow database could isolate load at scale, but one PostgreSQL service is simpler today.

## Application schema ownership

Alembic exclusively owns application tables. LangGraph owns its own checkpoint tables via `setup()`. Runtime `create_all()` is intentionally absent because it cannot safely express production schema evolution.

## Confidence policy

The weighted-deduction model is understandable and easy to inspect, but it is heuristic. Alternatives include:

- a policy matrix where specific code combinations map directly to decisions;
- a calibrated statistical model trained on reviewer outcomes;
- carrier-, lane-, or customer-specific thresholds;
- expected-loss optimization using invoice value and error cost.

The next mature step is to preserve rule findings while calibrating the routing policy on labelled history. A model should assist prioritization, not erase the underlying evidence.

## Tenant strategy

Tenant scope is carried through request dependencies, database queries, graph nodes, agent state, and worker payloads. This is necessary but not sufficient for a regulated production deployment.

Alternatives for stronger isolation:

- PostgreSQL row-level security with tenant session variables;
- separate schemas per tenant;
- separate databases and graph databases for high-value tenants.

Row-level security is the best next defense-in-depth step for a shared-database deployment.

## Authentication strategy

HTTP Basic bootstrap users minimize local setup. The demo identity is valid only in the demo tenant. This is explicitly a controlled-environment choice.

Production alternatives are OIDC/OAuth2 with an identity provider, short-lived signed tokens, role and permission claims, MFA, service accounts, and immutable identity in reviewer audit events.

## JSON evidence and rate cards

JSON keeps heterogeneous rate cards and read-as-a-whole evidence flexible. It avoids premature nullable tables for every pricing shape.

The trade-off is weaker database constraints and harder analytics. Frequently queried rate-card fields should eventually move into versioned relational rows while raw source documents remain JSON/object storage.

## Decisions that should not be changed casually

- Do not move financial math into prompts.
- Do not make Neo4j the silent source of truth.
- Do not resume a review with a newly generated thread ID.
- Do not let workers perform destructive shared-graph rebuilds.
- Do not create application tables at runtime outside Alembic.
- Do not authorize by a tenant header alone.
- Do not log full model prompts or credentials by default.
