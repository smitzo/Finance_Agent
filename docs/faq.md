# Frequently Asked Questions

## Product and domain

### Why is this an agent instead of a normal CRUD application?

The audit is a stateful sequence: collect relationship evidence, apply controls, resolve bounded ambiguity, decide, potentially pause, then resume after a human response. LangGraph makes those transitions and interrupts explicit. The exact checks are still ordinary Python functions.

### Why not send the whole invoice to an LLM and ask if it is correct?

Financial arithmetic and policy boundaries must be reproducible. The model is useful for fuzzy names and ambiguous contract notes, but it is not the authority for totals, weights, dates, or duplicate checks.

### What does confidence mean?

It is a routing heuristic derived from unique warning/error findings, plus an ambiguity penalty. It is not a statistical probability that the bill is correct.

### Why can a disputed bill finalize without human review?

The current policy treats sufficiently strong deterministic evidence as directly disputable. Only `flag` interrupts. A tenant policy could route all disputes to a human by changing the graph routing and tests.

### Why reject duplicates but dispute other errors?

A duplicate is structurally invalid for payment and is mapped to `reject`. Rate, contract, or weight problems may be legitimate invoices requiring a carrier dispute, so they map to `dispute`.

## Architecture

### Why are both PostgreSQL and Neo4j used?

PostgreSQL provides transactional truth, constraints, reporting, and migrations. Neo4j provides relationship traversal across carriers, contracts, lanes, shipments, BOLs, and bills. Neo4j is derived and can be rebuilt.

### Could PostgreSQL replace Neo4j?

Yes. Indexed joins and recursive CTEs may be sufficient at modest graph depth. Neo4j is justified when multi-hop relationship exploration, anomaly queries, and connected evidence become central enough to offset the extra operational complexity.

### Why Redis and Celery?

Agent runs can outlive HTTP requests and must not consume API process capacity. Celery supports independent workers, retry controls, late acknowledgement, and backpressure.

### Why not FastAPI `BackgroundTasks`?

Those tasks share the API process and can be lost during deployment or restart. They are suitable for small non-critical follow-up work, not durable audits.

### Why store checkpoints in PostgreSQL?

Human review can last hours or days. A PostgreSQL checkpoint lets the exact graph thread resume after processes restart. In-memory state cannot provide that guarantee.

### Why does Alembic not manage checkpoint tables?

The LangGraph saver versions its own schema. Alembic manages only application tables and excludes the checkpoint tables to avoid conflicting owners.

### Why is the code a modular monolith?

The domain is still cohesive, and one repository keeps contracts and changes easy to coordinate. API and workers are separate runtime processes, so the most important scaling boundary already exists without premature service fragmentation.

## Data and tenancy

### How is tenant isolation implemented?

The tenant is resolved from `X-Tenant-ID` and propagated through authorization, service queries, agent state, Celery payloads, and graph node keys. Production should add row-level security and identity-bound tenant claims.

### Is the tenant header sufficient authorization?

No. A trusted identity must be authorized for the tenant. The current bootstrap credentials are a local/demo boundary, not a production identity design.

### Why are rate cards and evidence JSON?

They vary in shape and are usually read as a whole. JSON avoids premature schema explosion. Frequently queried pricing fields should become versioned relational rows as the product matures.

### How are retries de-duplicated?

Clients can supply an idempotency key unique within tenant and workflow. Duplicate invoice number checks are separate because the same request and the same business invoice are different identities.

### What happens if PostgreSQL and Neo4j disagree?

PostgreSQL wins. Neo4j is a projection and should be rebuilt or reconciled.

## Agent and model behavior

### What happens when no model key is configured?

Exact checks still run. Contract overlap falls back to closest rate. Fuzzy carrier normalization cannot be confirmed and may produce an unknown-carrier outcome. Explanations fall back to deterministic text.

### How is hallucination limited?

The model can select only supplied carrier/contract identifiers; its choice is parsed and checked against candidates. It cannot write totals or bypass deterministic findings. Invalid output falls back.

### Why is there a circuit breaker?

A large batch should not repeatedly call a provider that is returning quota or rate-limit errors. The process-local cooldown stops the call storm while allowing exact controls to continue.

### Could embeddings replace carrier-name prompts?

Yes. A curated alias table plus string/embedding similarity would be cheaper and more controllable. It becomes attractive once enough labelled name variants exist.

### How should thresholds be chosen?

Use labelled historical decisions and the cost of false approvals versus unnecessary reviews. The current values are transparent defaults, not universal finance policy.

## Reliability and operations

### What survives a restart?

Committed bills, decisions, audit events, and LangGraph checkpoints survive. Redis persistence is enabled locally, but production queue guarantees depend on the managed Redis/Celery configuration.

### What is the largest current reliability gap?

The database commit and queue publish are separate operations. A transactional outbox is needed to guarantee that every committed pending bill is eventually enqueued.

### How is one bill traced across services?

The API accepts or creates `X-Correlation-ID`, returns it to the client, persists it on the bill, and includes it in the Celery task and structured logs alongside bill, tenant, and task IDs.

### How should worker throughput be increased?

Measure database, checkpoint-pool, model, and graph latency first. Then increase worker replicas/concurrency, use separate deterministic/AI queues, and protect interactive fairness.

### Why is worker prefetch set to one?

Agent tasks have variable duration. Prefetch one prevents a worker from reserving many tasks while other workers sit idle and provides clearer backpressure.

## Demo and testing

### Is demo data real customer data?

No. It is deterministic synthetic data using unmistakable demo identifiers and `.example` contact domains.

### What does the 120-bill demo prove?

It exercises 60 clean deterministic bills, 20 known-carrier contract ambiguities, 20 fuzzy-carrier ambiguities, and 20 explicit boundary/failure cases. It proves product paths, not production capacity or statistical accuracy.

### Why does demo loading use real workers?

The demo should exercise the same persistence, graph, queue, checkpoint, and decision path as normal intake. Otherwise it could hide integration defects.

### Which tests matter most after an architecture change?

Run unit rules, tenancy/graph tests, auth tests, demo-shape tests, worker/checkpoint tests, real PostgreSQL integration tests, Alembic drift checks, frontend production build, and Compose configuration validation.
