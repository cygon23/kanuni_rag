# Runbook

> Status: Phase 0 stub. Filled out in full during Phase 6 (PROJECT_SPEC.md
> §14) once there is a deployed system with real failure modes to document.
> At minimum this will cover: provider outage/fallback behavior, ingestion
> job stuck/failed, DB migration rollback, rotating API keys, and
> re-indexing after an embedding model change (§11).

## Local stack (today)

- Bring the stack up: `make dev` (`docker compose up --build`).
- Liveness: `curl http://localhost:8000/healthz`
- Readiness (checks the database): `curl http://localhost:8000/readyz`
- Tear down: `make down`
