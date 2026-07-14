# 0001. v1 corpus scoped to Bank of Tanzania only; engine stays institution-agnostic

## Context

Kanuni's mission (PROJECT_SPEC.md §1) is regulatory Q&A across East African
financial, tax, and trade regulation — potentially spanning the Bank of
Tanzania (BoT), TRA, FIU, EAC customs instruments, AML directives, and more.
Building a high-quality, citation-grounded, confidence-gated system depends
on complete, well-modeled coverage of whatever is ingested: a coherent
supersession graph, accurate metadata, and a golden evaluation dataset large
enough to measure retrieval and answer quality honestly.

## Decision

v1 ingests **Bank of Tanzania documents only** — acts, regulations,
circulars, and guidelines issued by BoT. This is a deliberate
depth-over-breadth choice: one issuing body makes complete coverage,
a coherent supersession graph, and a high-quality golden dataset achievable
within v1's scope.

Nothing in the engine may hardcode BoT, or any institution. Issuing body,
jurisdiction, and source definitions live entirely in `sources.yaml` and in
database rows (`documents.issuing_body`, `documents.jurisdiction`,
`documents.source_id` as a free-text slug — see ADR 0002). Adding TRA, FIU,
or EAC later must require zero engine code changes, not just zero *schema*
changes. This is verified by an integration test that ingests a fixture
from a fictional second source through the unmodified pipeline.

## Alternatives considered

- **Ingest multiple institutions from the start.** Rejected: coverage would
  be shallow across all of them, the supersession graph would be harder to
  validate (cross-institution relations are rarer and messier), and the
  golden dataset would need to be proportionally larger to have any
  per-institution statistical power — all before the retrieval/generation
  architecture itself is proven.
- **Hardcode BoT-specific fields or logic in the pipeline** (e.g. a
  `bot_reference_number` format parser baked into `versioning.py`). Rejected
  even though it would be faster short-term: it would make the "add TRA with
  zero engine changes" claim false, and that claim is the entire point of
  scoping down in the first place.

## Consequences

- `sources.yaml` is the only place a new issuing body is registered; the
  fixture-based extensibility test must keep passing as ingestion logic
  evolves.
- The golden evaluation dataset (§10) is BoT-only for v1; recall/precision
  numbers should not be read as generalizing to other institutions'
  document styles (different heading conventions, reference-number formats,
  etc.) until they're actually ingested and evaluated.
- Non-goals for v1 (TRA, FIU, EAC, BRELA corpora) are explicitly deferred to
  v2 as pure data additions, not architecture work.
