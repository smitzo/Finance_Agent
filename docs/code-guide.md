# Important Code Paths

This guide identifies methods that define product behavior. Small serializers and UI presentation helpers are intentionally omitted.

## API and authorization

| Method | Responsibility | Important invariant |
|---|---|---|
| `app.auth.require_current_user` | Validates bootstrap or demo credentials | Demo credentials work only for the configured demo tenant |
| `app.tenancy.tenant_from_header` | Resolves `X-Tenant-ID` | Every downstream service receives a normalized tenant |
| `app.api.routes._ingest_one_bill` | Validates workflow, ID, idempotency, duplicate state, persists, and optionally queues | Commit happens before enqueue |
| `app.api.routes.ingest_freight_bill` | Supports one bill or independent bulk outcomes | One invalid bulk item does not erase accepted items |
| `app.api.routes.submit_review` | Validates review state and queues a resume | Only a persisted `awaiting_review` thread can resume |
| `app.api.routes.load_and_process_demo_data` | Loads, projects, and queues the demo | Uses the same worker path as real intake |

## Service and persistence layer

| Method | Responsibility | Important invariant |
|---|---|---|
| `freight_service.create_bill` | Creates the ORM row and preserves unknown input fields in evidence | Only allow-listed fields reach ORM constructor |
| `freight_service.find_by_idempotency_key` | Finds retry-equivalent work | Key is scoped by tenant and workflow |
| `freight_service.find_duplicate_bill` | Pre-agent duplicate guard | Prefer carrier ID; fall back to normalized carrier name |
| `freight_service.persist_result` | Writes findings, evidence, decision, status, and audit events | Interrupted workflows become `awaiting_review` |
| `freight_service.apply_reviewer_decision` | Records reviewer input and returns bill to processing | Review metadata is persisted before resume enqueue |
| `demo_data_service.build_demo_dataset` | Builds deterministic synthetic reference and bill data | No external or real customer data |
| `demo_data_service.clear_demo_data` | Removes demo-prefixed records in dependency order | Non-demo records remain untouched |

## Agent execution

| Method | Responsibility | Important invariant |
|---|---|---|
| `worker.tasks.enqueue_bill` | Sends a new audit to Celery | API does not execute the graph |
| `execution.process_agent_for_bill` | Creates a unique durable thread, runs graph, persists outcome | New runs never reuse stale checkpoint threads |
| `execution.resume_agent_for_bill` | Updates the `human_review` node and resumes | Uses the exact thread stored on the bill |
| `checkpoint.initialize_agent_runtime` | Opens process-local psycopg pool and compiles graph | Pool is reused within one worker child only |
| `checkpoint.setup_checkpoint_schema` | Creates/upgrades LangGraph tables | Runs once before workers start |
| `agent.build_agent` | Declares nodes, edges, and conditional routing | `flag` is the only decision routed to interrupt |

## Agent nodes

| Node | Inputs used | Outputs produced |
|---|---|---|
| `load_context` | Bill, tenant, graph facade | Carrier, contracts, shipment, BOLs, prior weight, duplicates, graph anomalies |
| `validate` | Bill and loaded evidence | Contract-independent deterministic findings |
| `resolve_ambiguity` | Candidate contracts and blocker findings | Chosen contract, ambiguity note, contract-dependent findings |
| `decide` | De-duplicated findings and thresholds | Confidence and `auto_approve`, `flag`, `dispute`, or `reject` |
| `human_review` | Bill ID, confidence, preliminary decision | Durable interrupt and reviewer input |
| `finalize` | Final decision and findings | Explanation and final audit event |

## Validation methods

`app/agent/rules.py` is the finance-control boundary:

- `check_duplicate`
- `check_carrier_known`
- `check_contract_active`
- `check_rate`
- `check_min_weight`
- `check_fuel_surcharge`
- `check_base_charge`
- `check_weight_vs_bol`
- `check_uom_mismatch`
- `check_total_amount`
- `compute_confidence`

These functions return structured `Finding` values and do not call external services. Monetary comparison currently uses a relative 2% tolerance.

## Graph methods

`GraphService` is the backend-neutral facade. The agent depends on methods such as `get_contracts_for_lane`, `get_bols_for_shipment`, `find_duplicate_bill_ids`, and `detect_anomalies_for_bill`, not on Neo4j driver calls.

`MemoryGraphBackend` supports fast unit tests and restricted local runs. `Neo4jGraphBackend` owns constraints, Cypher projection, relationship traversal, and graph-native anomaly queries.

## LLM methods

- `normalize_carrier_name`: returns a known carrier ID or no match.
- `resolve_ambiguous_contract`: asks for one candidate ID; falls back to closest rate on unavailable or invalid output.
- `generate_explanation`: converts structured findings into operator text; falls back to a deterministic summary.
- `_call_llm`: selects provider, controls debug logging, handles errors, and enforces the circuit breaker.

Prompts receive only the evidence needed for their bounded task. Debug payload logging is off by default because prompts may contain business data.

## Safe modification checklist

Before changing a critical method, verify:

1. tenant scope remains explicit;
2. exact finance logic stays deterministic;
3. API execution remains short and enqueue-only;
4. workflow state can survive restarts;
5. evidence and audit events remain reconstructable;
6. old idempotent requests retain their semantics;
7. migration and model changes stay synchronized;
8. the demo and focused tests cover the new branch.
