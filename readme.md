# FreightFlow AI

FreightFlow AI is a multi-tenant freight-bill audit control tower. It validates carrier invoices against contracts, shipments, and bills of lading; uses bounded AI only for ambiguous context; and durably pauses uncertain cases for accountable human review.

The repository contains a React operations UI, FastAPI API, Celery worker fleet, Redis queue, PostgreSQL business state and LangGraph checkpoints, Neo4j evidence traversal, Alembic migrations, structured JSON logging, and a comprehensive synthetic demo.

## Product capabilities

- Ingest one bill or a bulk JSON array with optional idempotency keys.
- Check duplicates, carrier identity, contract dates, minimum weight, rates, base charges, fuel surcharges, BOL weight, UOM, and invoice totals.
- Traverse carrier, contract, lane, shipment, BOL, and prior-bill relationships.
- Resolve fuzzy carrier names and overlapping contracts through a constrained model path with deterministic fallbacks.
- Auto-approve clean bills, dispute/reject hard failures, and checkpoint review cases.
- Resume the exact paused workflow after API or worker restarts.
- Inspect evidence, explanations, audit history, review state, metrics, and correlation-aware logs.
- Operate tenant company and audit-partner profiles through the UI.
- Present the processing architecture through a backend-free, browser-local interactive demonstration.
- Exercise 120 synthetic bills across clean, ambiguity, boundary, and failure scenarios.

## Quick start

### Run the frontend-only showcase

The public demonstration needs only Node.js 20 or newer. It does not call a backend, database, graph service, queue, or paid model:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173/#demo> and choose **Process demo data**. The page follows an editable invoice through simulated API intake, queue handoff, a visualized Cypher/graph exchange, deterministic controls, optional bounded model reasoning, decision routing, and final JSON output.

Build the static artifact for free-tier hosting:

```bash
cd frontend
npm run build
npm run preview
```

Open <http://localhost:4173/#demo>, or publish `frontend/dist/` on any static host and link to `/#demo`. The simulated calls are visibly labelled; authenticated operations pages still require the complete backend. See [Frontend-only product demonstration](docs/frontend-only-demo.md) for its trust boundary, scenarios, and deployment notes.

### Complete-stack requirements

- Docker Engine with the Compose plugin.
- At least 4 GB free memory; 6 GB is more comfortable for builds plus Neo4j.
- Ports `3000`, `8000`, and `7474` available.

### Start the complete stack

```bash
cp .env.example .env

# Optional: add one key to exercise model-assisted carrier normalization.
# OPENAI_API_KEY=...
# or ANTHROPIC_API_KEY=...

docker compose up --build -d
docker compose ps
```

The first start builds both application images, applies every Alembic migration, initializes LangGraph checkpoint tables, loads reference seed data, and starts the API, worker, frontend, PostgreSQL, Redis, and Neo4j.

Open:

| Surface | URL |
|---|---|
| Product UI | <http://localhost:3000> |
| OpenAPI/Swagger | <http://localhost:8000/docs> |
| API health | <http://localhost:8000/health> |
| Neo4j Browser | <http://localhost:7474> |

### Choose a workspace

Local administrator:

```text
Tenant:   default
Username: admin
Password: admin
```

Isolated demo workspace:

```text
Tenant:   demo
Username: demo
Password: demo
```

The demo credentials are rejected outside tenant `demo`. The bootstrap administrator is intended only for controlled local development.

Verify a session from the command line:

```bash
curl -u demo:demo \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/session
```

## Run the comprehensive full-stack demo

Sign in to tenant `demo`, choose **Use demo data** on the overview, and wait for workers to drain the queue.

CLI equivalent:

```bash
curl -u demo:demo -X POST \
  -H 'X-Tenant-ID: demo' \
  -H 'X-Correlation-ID: demo-run-001' \
  http://localhost:8000/admin/demo/load

docker compose logs -f worker
```

The 120-bill portfolio contains:

| Cohort | Count | Coverage |
|---|---:|---|
| Deterministic baseline | 60 | Clean single-contract bills with complete evidence |
| AI-assisted ambiguity | 40 | 20 known-carrier contract overlaps and 20 fuzzy-carrier plus contract-overlap cases |
| Edge/control cases | 20 | Duplicate, rate, weight, total, surcharge, contract, missing evidence, UOM, minimum charge, and multi-BOL behavior |

Every bill records its demo scenario and expected behavior in `evidence`. The load response also returns cohort ID lists and a scenario catalogue. Without a model key, exact checks still run, overlapping contracts use the closest-rate fallback, and fuzzy carrier names may become unknown-carrier disputes.

See [Demo scenario catalogue](docs/demo-scenarios.md) for the complete matrix.

Check progress:

```bash
curl -u demo:demo \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/metrics
```

Demo loading returns `202`; final distributions are meaningful after `pending` and `processing` are zero.

Remove only synthetic records:

```bash
curl -u demo:demo -X DELETE \
  -H 'X-Tenant-ID: demo' \
  http://localhost:8000/admin/demo
```

## How the system works

```mermaid
flowchart LR
    UI[React + Nginx] -->|authenticated API| API[FastAPI]
    API -->|business state| PG[(PostgreSQL)]
    API -->|enqueue| REDIS[(Redis)]
    REDIS --> WORKER[Celery worker]
    WORKER -->|durable checkpoints and results| PG
    WORKER -->|evidence traversal| NEO[(Neo4j)]
    WORKER -. bounded ambiguity .-> LLM[OpenAI or Anthropic]
```

1. The API authenticates the caller, resolves the tenant, validates input, checks idempotency/duplicates, commits the bill, and enqueues work.
2. A worker creates a unique durable LangGraph thread and projects the bill into the graph.
3. The agent loads carrier, contract, shipment, BOL, prior-bill, and graph-anomaly context.
4. Deterministic Python rules evaluate exact facts. Hard blockers skip model calls.
5. A model may normalize a missing carrier ID or choose among allowed overlapping contracts. Unavailable or invalid output has a deterministic fallback.
6. Confidence and policy produce `auto_approve`, `flag`, `dispute`, or `reject`.
7. `flag` interrupts and checkpoints in PostgreSQL. A reviewer later resumes the same thread.
8. Final status, explanation, findings, evidence, and audit events are committed to PostgreSQL.

Read the [high-level design](docs/high-level-design.md), [low-level design](docs/low-level-design.md), and [functional and technical flows](docs/flows.md) for diagrams and invariants.

## Decision policy

The confidence score starts at `1.0`, subtracts `0.25` per unique error and `0.08` per unique warning, and subtracts `0.15` for genuine contract ambiguity.

| Default condition | Decision | Action |
|---|---|---|
| Duplicate finding | `reject` | Finalize |
| Confidence `>= 0.85` and no errors | `auto_approve` | Finalize |
| Confidence `<= 0.40` or hard carrier/weight error | `dispute` | Finalize |
| Remaining cases | `flag` | Durable human review |

This is an explainable routing heuristic, not a probability model. Production thresholds should be calibrated with labelled reviewer outcomes and false-approval cost.

## API essentials

Business endpoints use HTTP Basic authentication and `X-Tenant-ID`. The frontend sends the same headers through its `/api` proxy.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/session` | Read authenticated role, tenant, and demo status |
| `GET` | `/workflows` | List supported workflow definitions |
| `POST` | `/freight-bills` | Ingest one bill or an array and queue work |
| `GET` | `/freight-bills` | List tenant bills with limit/offset |
| `GET` | `/freight-bills/{id}` | Read complete result and evidence |
| `GET` | `/freight-bills/{id}/audit` | Read ordered audit events |
| `GET` | `/review-queue` | List interrupted cases |
| `POST` | `/review/{id}` | Submit `approve`, `dispute`, or `reject` |
| `GET` | `/metrics` | Read status, decision, and confidence metrics |
| `GET/PUT` | `/company` | Read or save the tenant company profile |
| `GET/POST` | `/partner-firms` | Read or upsert audit partners |
| `POST` | `/admin/rebuild-graph` | Rebuild the selected tenant projection |
| `POST` | `/admin/demo/load` | Load and queue the 120-bill demo |
| `DELETE` | `/admin/demo` | Remove only demo-prefixed records |
| `DELETE` | `/admin/data?confirm=DELETE_ALL` | Remove all selected-tenant application data |
| `GET` | `/health`, `/health/db`, `/health/graph` | Liveness and dependency probes |

### Ingest a bill

```bash
curl -u admin:admin -X POST http://localhost:8000/freight-bills \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: default' \
  -H 'X-Correlation-ID: import-2026-08-17-001' \
  -d '{
    "idempotency_key": "erp-freight-2026-00821",
    "carrier_id": "CAR001",
    "carrier_name": "Safexpress Logistics",
    "bill_number": "SFX/2026/00821",
    "bill_date": "2026-08-17",
    "shipment_reference": "SHP-2025-002",
    "lane": "DEL-BLR",
    "billed_weight_kg": 850,
    "rate_per_kg": 15,
    "billing_unit": "kg",
    "base_charge": 12750,
    "fuel_surcharge": 1020,
    "gst_amount": 2479,
    "total_amount": 16249
  }'
```

The response is `202 Accepted`. Keep the returned `X-Correlation-ID` to trace the bill across API and worker logs.

### Submit a review

```bash
curl -u admin:admin -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Tenant-ID: default' \
  http://localhost:8000/review/FB-EXAMPLE \
  -d '{
    "reviewer_decision": "approve",
    "reviewer_notes": "Contract and delivery evidence verified."
  }'
```

The bill must currently be `awaiting_review` and have a persisted LangGraph thread.

## Configuration

Copy `.env.example` to `.env`. Compose overrides internal service addresses, so local container DNS remains correct even when host defaults differ.

| Variable | Default or example | Purpose |
|---|---|---|
| `DATABASE_URL` | local PostgreSQL DSN fallback | Application and checkpoint database |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Short-lived task results |
| `CELERY_CONCURRENCY` | `4` in Compose command | Worker child count |
| `CHECKPOINT_POOL_SIZE` | `5` | Per-worker-process checkpoint pool cap |
| `DEFAULT_TENANT_ID` | `default` | Fallback tenant when header is absent |
| `ADMIN_USERNAME/PASSWORD` | `admin/admin` | Local bootstrap identity |
| `DEMO_TENANT_ID/USERNAME/PASSWORD` | `demo/demo/demo` | Tenant-restricted demo identity |
| `GRAPH_BACKEND` | `neo4j` | `neo4j` or test/local `memory` |
| `NEO4J_URI/USER/PASSWORD/DATABASE` | environment-specific | Graph connection |
| `LLM_PROVIDER` | `openai` in `.env.example` | Preferred `openai` or `anthropic` client |
| `LLM_OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model name |
| `LLM_ANTHROPIC_MODEL` | `claude-3-5-haiku-latest` | Anthropic model name |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | empty | Optional model credentials |
| `LLM_DEBUG_PAYLOADS` | `false` | Logs prompts/responses; avoid with sensitive data |
| `AUTO_APPROVE_THRESHOLD` | `0.85` | Direct approval boundary |
| `DISPUTE_THRESHOLD` | `0.40` | Low-confidence dispute boundary |

See `.env.example` for logging, circuit-breaker, graph-pool, and other settings.

## Migrations and durable state

Application schema changes are owned only by Alembic:

```bash
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic upgrade head
```

The migration chain includes the core baseline, tenant/workflow columns, idempotency, company/partner/auth models, and worker observability columns.

LangGraph separately owns `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` through `AsyncPostgresSaver.setup()`. The one-shot `migrate` service initializes them before prefork workers start. Runtime `Base.metadata.create_all()` is intentionally not used.

## Development workflow

### Recommended: all services in Docker

Use the quick-start stack and rebuild only changed services:

```bash
docker compose up --build -d api worker frontend
docker compose logs -f api worker
```

PostgreSQL and Redis are intentionally not published to host ports by the default Compose file. This reduces accidental exposure.

### Frontend hot reload

Run the backend stack in Docker, then start Vite:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to `http://localhost:8000`.

### Host-run backend

Create a Python 3.12 environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Provide reachable PostgreSQL, Redis, and Neo4j endpoints, then run:

```bash
alembic upgrade head
python scripts/checkpoint_setup.py
python scripts/seed_loader.py

uvicorn app.main:app --reload --port 8000
celery -A app.worker.celery_app:celery_app worker --loglevel=INFO
```

Run API and worker in separate terminals. The default Compose databases are internal-only; use an explicit Compose override or external development services if host processes need them.

## Tests and verification

### Fast local checks

```bash
.venv/bin/pytest -q

cd frontend
npm ci
npm run build
```

Integration tests skip unless `TEST_DATABASE_URL` points to a migrated PostgreSQL database:

```bash
TEST_DATABASE_URL='postgresql+asyncpg://USER:PASS@HOST:5432/TEST_DB' \
  .venv/bin/pytest -m integration -q
```

Use a dedicated test database. The suite creates tenant-scoped records and checkpoint tables and cleans its bill/audit rows.

Additional release checks:

```bash
alembic check
docker compose config --quiet
git diff --check
```

The integration suite verifies migrated worker columns, service persistence, audit results, and a real `AsyncPostgresSaver` checkpoint round trip.

## Observability

API and worker events are JSON on stdout and in the rotating `logs/app.log` file. Useful fields include:

- `correlation_id`
- `freight_bill_id`
- `tenant_id`
- `celery_task_id`
- `http_method` and `http_path`
- `logger`, `level`, and `timestamp`

```bash
docker compose logs -f api worker
```

Clients may supply `X-Correlation-ID`; otherwise the API creates and returns one. The same ID is persisted and propagated to Celery.

## Stop, reset, and troubleshoot

```bash
# Stop containers and retain data volumes
docker compose down

# Inspect recent service logs
docker compose logs --tail=200 api worker migrate postgres redis neo4j frontend

# Remove containers and all Compose-managed product data
docker compose down -v
```

`down -v` permanently removes the local PostgreSQL, Redis, and Neo4j volumes. Use `DELETE /admin/demo` when only synthetic records should be cleared.

Common checks:

- API cannot start: inspect `migrate` and PostgreSQL health first.
- Worker remains unhealthy: inspect Redis connectivity and Celery worker name/ping output.
- Graph health fails: verify `NEO4J_PASSWORD` is identical for the app and Neo4j service.
- Model paths fall back: verify provider selection, key, quota, and circuit-breaker logs.
- UI API errors after restart: rebuild/restart frontend only if Nginx configuration changed; its upstream dynamically re-resolves Docker DNS.

## Repository map

```text
app/api/                 FastAPI routes
app/agent/               LangGraph nodes, exact rules, LLM adapter, checkpoints
app/services/            Persistence, graph, demo, and admin services
app/worker/              Celery application and task boundary
app/models/              SQLAlchemy models
app/tests/               Unit and PostgreSQL integration tests
frontend/src/            React operations UI
migrations/versions/     Ordered Alembic schema history
scripts/                 Seed and checkpoint setup commands
docs/                    Product, design, flows, decisions, edge cases, FAQ
seed_data.json           Baseline reference and example records
docker-compose.yml       Complete local topology
```

## Documentation

- [Documentation index](docs/README.md)
- [Project overview](docs/project-overview.md)
- [High-level design](docs/high-level-design.md)
- [Low-level design](docs/low-level-design.md)
- [Functional and technical flows](docs/flows.md)
- [Important code paths](docs/code-guide.md)
- [Architecture decisions and alternatives](docs/architecture-decisions.md)
- [Edge cases and failure handling](docs/edge-cases.md)
- [Improvement and scaling roadmap](docs/improvements.md)
- [Frequently asked questions](docs/faq.md)
- [Frontend-only product demonstration](docs/frontend-only-demo.md)
- [Demo scenario catalogue](docs/demo-scenarios.md)

## Production boundary

Before an internet-facing deployment, complete the Priority 0 work in the [improvement roadmap](docs/improvements.md): external identity, RBAC, immutable reviewer identity, restricted CORS/TLS/rate limiting, strict finance input validation, row-level tenant protection, transactional outbox, and idempotent worker leases. Use managed data services, secret management, backups, centralized telemetry, and a release migration job.
