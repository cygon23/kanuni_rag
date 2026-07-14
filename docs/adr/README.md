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

No ADRs exist yet — Phase 0 made scaffolding decisions not yet covered by
the spec (see the Phase 0 handoff summary); write those up as ADR 0001+
before Phase 1 begins.
