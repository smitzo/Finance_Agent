# Freight Bill Processor

A stateful LangGraph agent that automatically validates carrier freight bills against contracts, shipments, and bills of lading — with human-in-the-loop review for low-confidence cases.

Check it out at: https://finance-agent-889865964505.europe-west1.run.app/docs

---

## Quick Start

### Option A — Docker (recommended)

```bash
# 1. Clone / unzip the project
cd finance_agent

# 2. Add your LLM key
cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY or OPENAI_API_KEY

# 3. Start everything
docker-compose up --build

# 4. The API is now at http://localhost:8000
# Seed data is auto-loaded on container startup
```

### Option B — Local (no Docker)

```bash
# Prerequisites: Python 3.12+, Postgres running locally

python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Create env file
cp .env.example .env
# Windows PowerShell:
# Copy-Item .env.example .env
# then edit .env and set one LLM key:
#   ANTHROPIC_API_KEY=...
#   or OPENAI_API_KEY=...
# Optional resilience toggles:
#   LLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS=60
#   MAX_CONCURRENT_AGENT_RUNS=8

# Load seed data
python -m app.seed_loader

# Run API
uvicorn app.main:app --reload --port 8000

# Logs are printed to terminal and written to:
#   logs/app.log (with rotation)
```

### Run Tests

```bash
python -m pytest app/tests/ -v
```

### Resilience Tests (bulk + quota protection)

```bash
python -m pytest app/tests/test_resilience.py -v
```

### Run Smoke Test

With API running locally:

```bash
python scripts/smoke_test.py
```

If your API runs on a different host/port:

```bash
python scripts/smoke_test.py http://127.0.0.1:8000
```

### Demo and Admin Data

With the API running, open Swagger UI at `http://localhost:8000/docs` and use the **Admin** endpoints:

- `POST /admin/demo/load`: creates 20 demo freight bills with demo carriers, contracts, shipments, and BOLs, then queues all bills for agent processing. The first 10 are deterministic; the last 10 omit `carrier_id` and use overlapping contracts so LLM carrier normalization and ambiguity-resolution logs are exercised.
- `DELETE /admin/demo`: deletes only records with demo prefixes (`DEMO-*`, `CAR-DEMO*`) and rebuilds the in-memory graph.
- `DELETE /admin/data?confirm=DELETE_ALL`: deletes all carriers, contracts, shipments, BOLs, freight bills, and audit logs while keeping the schema intact.

CLI alternative:

```bash
python scripts/demo_data.py load
python scripts/demo_data.py clear
```

---

## Deploy on GCP (Cloud Run + Secret Manager)

You do not need a `.env` file in production. Use Secret Manager and inject secrets as environment variables at deploy time.

```bash
# 0) Set your values
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export REPO="freight-api"
export IMAGE="freight-bill-processor"
export SERVICE="freight-bill-processor"

# 1) Enable required APIs
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project $PROJECT_ID

# 2) Artifact Registry (one-time)
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION --project=$PROJECT_ID
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# 3) Build & push image
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}:v1 .
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}:v1

# 4) Create/update secrets (examples)
printf "postgresql+asyncpg://USER:PASS@HOST:5432/DB?ssl=require" | gcloud secrets create DATABASE_URL --data-file=- --project $PROJECT_ID || true
printf "your-openai-key" | gcloud secrets create OPENAI_API_KEY --data-file=- --project $PROJECT_ID || true
printf "openai" | gcloud secrets create LLM_PROVIDER --data-file=- --project $PROJECT_ID || true

# Add new versions if secret already exists
printf "postgresql+asyncpg://USER:PASS@HOST:5432/DB?ssl=require" | gcloud secrets versions add DATABASE_URL --data-file=- --project $PROJECT_ID
printf "your-openai-key" | gcloud secrets versions add OPENAI_API_KEY --data-file=- --project $PROJECT_ID
printf "openai" | gcloud secrets versions add LLM_PROVIDER --data-file=- --project $PROJECT_ID

# 5) Deploy Cloud Run service
gcloud run deploy $SERVICE \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}:v1 \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,LLM_PROVIDER=LLM_PROVIDER:latest
```

After deploy, open:
- `https://<cloud-run-url>/docs` for Swagger UI
- `https://<cloud-run-url>/health` for liveness


## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | `/freight-bills` | Ingest a freight bill, triggers agent (async) |
| GET | `/freight-bills` | List all bills |
| GET | `/freight-bills/{id}` | Get bill state, decision, evidence |
| GET | `/freight-bills/{id}/audit` | Full audit trail for a bill |
| GET | `/review-queue` | Bills waiting for human review |
| POST | `/review/{id}` | Submit reviewer decision, resume agent |
| GET | `/metrics` | Agent performance summary |
| GET | `/health` | Liveness check |
| GET | `/health/db` | DB connectivity check (`SELECT 1`) |
| POST | `/admin/demo/load` | Load and process demo data |
| DELETE | `/admin/demo` | Remove demo data |
| DELETE | `/admin/data?confirm=DELETE_ALL` | Remove all application data |

### Example: Ingest a bill

```bash
curl -X POST http://localhost:8000/freight-bills \
  -H "Content-Type: application/json" \
  -d '{
    "id": "FB-2025-101",
    "carrier_id": "CAR001",
    "carrier_name": "Safexpress Logistics",
    "bill_number": "SFX/2025/00234",
    "bill_date": "2025-02-15",
    "shipment_reference": "SHP-2025-002",
    "lane": "DEL-BLR",
    "billed_weight_kg": 850,
    "rate_per_kg": 15.00,
    "base_charge": 12750.00,
    "fuel_surcharge": 1020.00,
    "gst_amount": 2479.00,
    "total_amount": 16249.00
  }'
```

### Example: Bulk ingest (array payload)

Use a JSON array (`[...]`), not comma-separated standalone objects:

```bash
curl -X POST http://localhost:8000/freight-bills \
  -H "Content-Type: application/json" \
  -d '[
    {
      "id": "FB-2025-101",
      "carrier_id": "CAR001",
      "carrier_name": "Safexpress Logistics",
      "bill_number": "SFX/2025/00234",
      "bill_date": "2025-02-15",
      "shipment_reference": "SHP-2025-002",
      "lane": "DEL-BLR",
      "billed_weight_kg": 850,
      "rate_per_kg": 15.00,
      "base_charge": 12750.00,
      "fuel_surcharge": 1020.00,
      "gst_amount": 2479.00,
      "total_amount": 16249.00
    },
    {
      "id": "FB-2025-109",
      "carrier_id": "CAR001",
      "carrier_name": "Safexpress Logistics",
      "bill_number": "SFX/2025/00234",
      "bill_date": "2025-02-15",
      "shipment_reference": "SHP-2025-002",
      "lane": "DEL-BLR",
      "billed_weight_kg": 850,
      "rate_per_kg": 15.00,
      "base_charge": 12750.00,
      "fuel_surcharge": 1020.00,
      "gst_amount": 2479.00,
      "total_amount": 16249.00
    }
  ]'
```

### Example: Submit a review

```bash
curl -X POST http://localhost:8000/review/FB-2025-102 \
  -H "Content-Type: application/json" \
  -d '{"reviewer_decision": "approve", "reviewer_notes": "Verified — CC-2025-SFX-003 applies"}'
```

---

## Schema Design

### Relational (Postgres)

| Table | Purpose |
|-------|---------|
| `carriers` | Master carrier registry |
| `carrier_contracts` | Contracts with rate cards stored as JSONB |
| `shipments` | Individual shipments with status |
| `bills_of_lading` | Delivery confirmations per shipment |
| `freight_bills` | Incoming bills with processing state, evidence JSONB |
| `audit_logs` | Append-only event log per bill |

**Why rate cards in JSONB?** Rate cards are heterogeneous — some are per-kg, some are FTL with alternate rates, some have mid-term revisions. A normalized `rate_card_rows` table would require nullable columns for every combination. JSONB keeps the structure flexible and queryable enough for our access patterns (always read the whole rate card for a contract).

**Why `evidence` as JSONB on FreightBill?** The evidence chain is a structured blob that travels with the bill and is always read whole. No need to normalize it.

### Graph (NetworkX, in-memory)

```
Carrier ──has_contract──► Contract ──covers_lane──► Lane
   │                          │
   └──has_shipment──► Shipment ──has_bol──► BOL
                          ▲
                    FreightBill ──references──►┘
```

**Why NetworkX instead of Neo4j?**  
The seed data has ~30 nodes and ~50 edges. At this scale, an in-memory NetworkX graph is:
- Zero infrastructure overhead (no extra container)
- Rebuilt from Postgres at startup in <100ms
- Sufficient for all traversal patterns we need (carrier→contracts→lanes, shipment→BOLs, FB→prior bills)

With Neo4j you'd add Cypher queries, a driver, connection pooling, and a container — real overhead for a problem that doesn't need it yet. The graph is rebuilt on startup so it stays consistent with Postgres.

**When to switch to Neo4j:** If the graph grows to millions of nodes, or if you need complex multi-hop queries across carriers (e.g. "find all shipments with rate anomalies across carriers on overlapping lanes"), then Neo4j's native indexes and Cypher become worth it.

---

## Confidence Scoring

Confidence is computed by `rules.compute_confidence()` from the `ValidationResult`:

```
score = 1.0
for each finding:
    error  → -0.25
    warn   → -0.08
score = clamp(score, 0.0, 1.0)

# Additional deduction in agent:
if multiple contracts matched (ambiguity) → -0.15
```

**Decision thresholds:**

| Confidence | Decision |
|-----------|----------|
| ≥ 0.80 AND no errors | `auto_approve` |
| ≤ 0.40 OR critical error (duplicate, unknown carrier, weight mismatch) | `dispute` |
| Everything else | `flag` → human review |

**What goes into the score:**

- Duplicate check (error = -0.25)
- Carrier known (error = -0.25)
- Contract active on bill date (error = -0.25)
- Minimum weight eligibility when a contract rate row specifies `min_weight_kg`
- Rate within 2% tolerance (error or warn depending on magnitude)
- Fuel surcharge correct (handles mid-term revisions)
- Base charge = weight × rate ≥ min_charge
- Billed weight vs BOL actual (accounts for prior bills on partial shipments)
- Total internal consistency (base + fsc + gst = total)
- UOM mismatch (FTL contract vs per-kg billing)

---

## Human-in-the-Loop Pattern

The agent uses LangGraph's `interrupt()` for real pause/resume — not a workaround:

```
decide() → confidence < threshold
    │
    ▼
human_review node calls interrupt({bill_id, confidence, decision})
    │
    ░ Agent state serialized to MemorySaver (thread_id stored in DB)
    ░ POST /review/{id} called by ops team
    │
    ▼
agent.update_state(config, {reviewer_decision: "approve"}, as_node="human_review")
agent.astream(None, config)   ← resumes from after interrupt()
    │
    ▼
finalize() → writes final state to DB
```

The `thread_id` (stored on `FreightBill.thread_id`) is the key that lets us resume the exact paused graph state. In production you'd replace `MemorySaver` with `AsyncPostgresSaver` so state survives API restarts.

---

## LLM Usage (Minimal and Intentional)

LLM calls are isolated to `llm_service.py` and used only for:

1. **Fuzzy carrier name matching** — `"Gati KWE Logistics"` has no carrier_id; LLM matches against known carriers. Deterministic rules can't do this.
2. **Ambiguous contract resolution** — when 3 contracts cover the same lane (FB-2025-102), the LLM picks the best match based on rate and notes. A rule-based tie-break would be arbitrary.
3. **Human-readable explanations** — converts structured findings into a 2-3 sentence summary for the ops reviewer.

All charge math, date checks, weight validation, and rate comparisons are deterministic rules in `rules.py`. This is the right boundary: LLM for fuzzy reasoning, rules for verifiable arithmetic.

---

## How Each Seed Bill Is Handled

| Bill | Scenario | Expected Decision |
|------|----------|-------------------|
| FB-2025-101 | Clean match | `auto_approve` |
| FB-2025-102 | 3 overlapping contracts, no shipment ref | `flag` (LLM resolves contract, ambiguity -0.15) |
| FB-2025-103 | Partial delivery, 800kg of 2000kg | `auto_approve` if weight checks out |
| FB-2025-104 | Over-billing (1500kg billed, 1200kg delivered) | `dispute` (WEIGHT_MISMATCH error) |
| FB-2025-105 | Rate drift +8.75% | `flag` (RATE_MISMATCH error) |
| FB-2025-106 | Expired contract | `dispute` (CONTRACT_EXPIRED error) |
| FB-2025-107 | FTL vs per-kg UOM | `flag` (UOM handled, but ambiguity remains) |
| FB-2025-108 | Revised fuel surcharge | `auto_approve` (revision logic handles it) |
| FB-2025-109 | Duplicate of FB-2025-101 | `dispute` (DUPLICATE_BILL error) |
| FB-2025-110 | Unknown carrier (Gati KWE) | `dispute` after LLM fuzzy match fails |

---

## Trade-offs and What I'd Do Differently

**Trade-offs made deliberately:**

- **MemorySaver over PostgresSaver**: State is lost on restart. Fine for a 48h assignment, but in production you'd use `langgraph-checkpoint-postgres`. The swap is one line.
- **Background tasks over Celery/RQ**: FastAPI's `BackgroundTasks` is simple and works for the demo. At volume you'd want a proper task queue so agent runs survive API pod restarts.
- **NetworkX over Neo4j**: Right call for this data scale. See Graph section above.
- **All disputed/flagged bills go to human review**: A production system might auto-reject clear duplicates without human review. I chose conservative behaviour — ops teams prefer to see everything initially.

**With more time:**
- Replace `MemorySaver` with `AsyncPostgresSaver` for durable state
- Add Alembic migrations instead of `create_all`
- Add a Celery worker for agent execution (decouple from API process)
- More test coverage: integration tests with a real DB using `pytest-asyncio`
- GCP deployment: Cloud Run (API) + Cloud SQL (Postgres) + Secret Manager
- Structured logging with correlation IDs per freight bill
