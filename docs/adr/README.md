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
- [0001 — v1 corpus scoped to Bank of Tanzania only](0001-v1-corpus-scoped-to-bank-of-tanzania.md)
- [0002 — `source_id` as a free-text slug, no `sources` table](0002-source-id-free-text-slug.md)
- [0003 — raw rerank score stored as confidence, tier derived at read time](0003-raw-rerank-score-stored-as-confidence.md)
- [0004 — per-language `tsvector` config for Swahili sparse retrieval](0004-swahili-full-text-search-config.md)
- [0005 — uv workspace over separate projects](0005-uv-workspace-over-separate-projects.md)
- [0006 — bun over pnpm for JS tooling](0006-bun-over-pnpm-for-js-tooling.md)

Still required per §15 and not yet written: hybrid retrieval + RRF choice;
bge-m3 embedding choice; confidence-threshold calibration method;
Postgres-backed jobs vs. a dedicated queue; chunking strategy; API-key auth
(v1) vs. OAuth (deferred). These land as their respective phases (2, 3, 1)
implement the underlying decision.
