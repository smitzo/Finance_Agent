# FreightFlow AI - Implementation Context

Last updated: 2026-08-17

## Product objective

Deliver a production-shaped freight-bill audit platform with a polished operator experience, durable human-in-the-loop agent state, independently scalable workers, migration-only database provisioning, real PostgreSQL integration coverage, and traceable structured logs.

## Current workstream

This file is the compact context cache for the current productization pass. Update it when an architectural decision, completed milestone, validation result, or blocker changes. Detailed user-facing setup belongs in `readme.md`; focused product and engineering explanations belong under `docs/`; `understanding.md` is only a compatibility index.

## Confirmed requirements

- Replace LangGraph `MemorySaver` with `AsyncPostgresSaver`.
- Make Alembic the only application-schema provisioning path; remove runtime `create_all()` calls.
- Execute and resume agents in Celery workers, never in FastAPI background tasks.
- Add real-PostgreSQL async integration tests using `pytest-asyncio`.
- Emit JSON logs with request correlation IDs and freight-bill IDs.
- Build a complete, intuitive SaaS landing and operations dashboard.
- Replace the existing README with an accurate end-to-end operator guide.
- Provide a transparently simulated, frontend-only product walkthrough for static hosting without backend infrastructure.

## Architecture decisions

- PostgreSQL remains the transactional source of truth and also stores LangGraph checkpoints.
- Redis is the Celery broker/result backend; API processes only validate, persist, and enqueue.
- Celery tasks receive the originating correlation ID so API and worker logs can be joined.
- Alembic receives a true legacy baseline migration so a fresh database can reach `head` without SQLAlchemy `create_all()`.
- The one-shot migration service initializes LangGraph-owned tables before Celery prefork children start.
- Neo4j full rebuilds are owned by API/admin flows; worker processes only add bill nodes so concurrent tasks never destructively rebuild the shared graph.
- The UI remains React + TypeScript + Tailwind and gains first-class bills, review, analytics, company, and partner surfaces.
- The Lightouz URL could not be resolved from the execution environment on 2026-08-07, so the UI direction uses an original premium B2B control-tower system rather than copied page structure or assets.
- Demo primary keys include a stable tenant fingerprint because the current relational models use global primary keys even though business reads are tenant-scoped.
- Graph rate outliers compare against the highest applicable overlapping-contract rate; comparing against the cheapest rate falsely flags valid premium contracts.
- A submitted carrier ID is considered known only after it resolves to carrier reference data.
- The public demo uses a hash route and browser-local synthetic processing so static hosts need no rewrite rule or runtime service; every simulated API, graph, and model exchange remains labelled.
- The public demo processes a default 10-bill portfolio from `frontend/demo/demo-bills.json`, reports aggregate outcomes, and retains a per-bill evidence and service-exchange drill-down.

## Baseline evidence

- Git branch: `main`, initially clean against `origin/main`.
- Backend baseline: 36 unit tests passed.
- Frontend baseline command was initially invoked from the repository root and failed because `package.json` lives in `frontend/`; validation must run from that directory.
- Initial Docker startup ran `alembic upgrade head`, but migration `0001` assumed core tables already existed.
- Initial runtime schema creation existed in both `app/main.py` and `scripts/seed_loader.py`.
- Initial agent execution and review resume used FastAPI `BackgroundTasks` plus an in-memory `MemorySaver` singleton.

## Progress

- [x] Repository and baseline audit
- [x] Context cache created
- [x] Durable LangGraph checkpoint runtime
- [x] Celery worker execution and review resume
- [x] Migration-only fresh database bootstrap
- [x] Correlation-aware structured logging
- [x] Real PostgreSQL integration tests
- [x] Full frontend redesign
- [x] README and architecture documentation refresh
- [x] Monolithic understanding guide split into focused public documentation
- [x] Comprehensive tenant-safe 120-bill demo scenario matrix
- [x] Frontend-only interactive processing and evidence-graph demonstration
- [x] Ten-bill frontend batch demonstration with standalone JSON fixture and per-result trace selection
- [x] Final backend, migration, worker, and frontend validation

## Validation log

Append concise results here as checks run.

- 2026-08-07: `.venv/bin/pytest -q` -> 36 passed.
- 2026-08-07: final `.venv/bin/pytest -q` -> 42 passed, 3 integration tests skipped unless explicitly enabled.
- 2026-08-07: real PostgreSQL integration suite -> 3 passed, 42 deselected.
- 2026-08-07: final Python 3.12 API image -> 42 passed, 3 skipped; in-container PostgreSQL integration -> 3 passed, 42 deselected.
- 2026-08-07: `alembic check` against the migrated PostgreSQL test database -> no new upgrade operations detected.
- 2026-08-07: `npm run build` -> production bundle built successfully (1,603 modules).
- 2026-08-07: Docker Compose -> API, frontend, worker, PostgreSQL, Redis, and Neo4j healthy; one-shot migration exited 0.
- 2026-08-07: Docker E2E -> 120 demo bills drained through Celery with zero `agent_error` audit entries for correlation `docker-e2e-clean-20260807`.
- 2026-08-07: durable review E2E -> `DEMO-FB-001` resumed from PostgreSQL checkpoint and finalized as approved.
- 2026-08-07: startup defects found and resolved during Docker acceptance: missing psycopg binary wrapper, nested Neo4j map properties, concurrent checkpoint setup, destructive per-worker graph rebuilds, and an IPv6-only frontend health probe target.
- 2026-08-07: rolling-restart proxy validation found and resolved stale Nginx DNS; the frontend upstream now re-resolves Docker service addresses.
- 2026-08-17: `.venv/bin/pytest -q` -> 49 passed, 3 PostgreSQL integration tests skipped unless explicitly enabled.
- 2026-08-17: real PostgreSQL integration suite in the API container -> 3 passed, 49 deselected; `alembic check` -> no new upgrade operations detected.
- 2026-08-17: frontend production build -> 1,603 modules transformed successfully; Compose configuration and `git diff --check` passed.
- 2026-08-17: live tenant-scoped demo -> 120/120 bills reached persisted outcomes: 87 approved, 23 disputed, 9 awaiting review, 1 rejected. Cleanup removed only the 120 synthetic bills and related demo records; final demo tenant bill count was zero.
- 2026-08-17: live demo validation exposed and fixed cross-tenant demo primary-key collisions, unresolved carrier IDs being treated as known, and false graph rate outliers on valid premium contracts.
- 2026-08-17: frontend-only demo -> production build transformed 1,605 modules; a headless-browser click flow reached the completed timeline, evidence graph, Cypher request, decision, and final output. Backend tests remained 49 passed and 3 skipped; Compose configuration and `git diff --check` passed.
- 2026-08-17: frontend batch demo -> standalone JSON fixture loaded 10 bills across six control paths; the browser click flow rendered exactly 10 result rows with aggregate outcomes and per-bill trace selection. Production build transformed 1,606 modules, backend tests remained 49 passed and 3 skipped, and `git diff --check` passed.

## Known follow-ups

- Replace bootstrap HTTP Basic credentials with database-backed authentication before an internet-facing deployment.
- Production deployment must run API, worker, PostgreSQL, Redis, and Neo4j as separately managed services.
