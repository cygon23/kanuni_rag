# Architecture Decision Records

One file per decision, named `NNNN-title-with-dashes.md`. Template
(PROJECT_SPEC.md §15):

```markdown
# NNNN. Title

## Context
## Decision
## Alternatives considered
## Consequences
```

Required at minimum (§15): hybrid retrieval + RRF choice; bge-m3 embedding
choice; confidence-threshold calibration method; Postgres-backed jobs vs. a
dedicated queue; chunking strategy; API-key auth (v1) vs. OAuth (deferred).

Existing:
- [0001 — bun over pnpm for JS tooling](0001-bun-over-pnpm-for-js-tooling.md)

Several other Phase 0 scaffolding decisions (documented in the Phase 0
handoff summary but not yet written up as formal ADRs) are still pending
before Phase 1 begins.
