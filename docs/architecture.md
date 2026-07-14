# Architecture

> Status: Phase 0 (skeleton & spine). This document will grow with each
> build phase in PROJECT_SPEC.md §14. For now it records the shape of the
> system as scaffolded, not yet its runtime behavior.

## Overview

Kanuni is two deployable Python services (API, ingestion worker) plus a
Next.js frontend, sharing a single Postgres (+ pgvector) database and the
`packages/shared` TypeScript types. There is no direct service-to-service
call path in v1 — see PROJECT_SPEC.md §5 for the full query and ingestion
flow diagrams.

## Services

- **apps/api** — FastAPI service. Owns the query path and admin/ingestion
  HTTP surface. See PROJECT_SPEC.md §8 for the query path spec.
- **apps/ingestion** — pipeline worker + `kanuni ingest` CLI. Owns document
  fetch, extraction, chunking, embedding, and indexing. See §7.
- **apps/web** — Next.js frontend. See §9.

## Data

Schema lives in `infra/migrations/` (dbmate) and is documented in
[data-model.md](data-model.md).
