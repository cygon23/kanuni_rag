# 0004. Per-language `tsvector` configuration for sparse retrieval

## Context

PROJECT_SPEC.md §2 states multilingual support (English + Swahili) is a
hard requirement, and `bge-m3` (dense retrieval) is chosen specifically for
its multilingual coverage. Sparse retrieval (§2, §8.1) uses PostgreSQL
full-text search (`tsvector` / `websearch_to_tsquery` / `ts_rank_cd`).
Migration `0001` defines `chunks.content_tsv` as
`GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` — a single,
fixed text-search configuration. PostgreSQL ships no `swahili` FTS
configuration, so Swahili chunks indexed under `'english'` get no
stemming/stopword handling appropriate to the language, silently degrading
sparse retrieval quality for Swahili queries even though dense retrieval
handles Swahili natively via bge-m3.

This gap was identified during Phase 0 scaffolding and deliberately
deferred rather than guessed at, per §7 stage 4's "on validation failure ...
do not guess" spirit applied here to search-quality decisions generally.

## Decision

Use PostgreSQL's built-in `'simple'` configuration (tokenizes without
language-specific stemming, but at least indexes Swahili tokens as
themselves rather than mis-stemming them under English rules) for documents
where `documents.language = 'sw'`, and keep `'english'` for
`documents.language = 'en'`. The correct `regconfig` is selected **per
document**, not globally.

This is recorded now, as the decision, but **implemented in Phase 2**
alongside the rest of the retrieval path — Phase 1 ships with the fixed
`'english'` configuration from migration `0001` unchanged, since sparse
retrieval isn't exercised until Phase 2 and Phase 1 must not touch
retrieval code.

Implementation sketch for Phase 2 (not yet built): `chunks.content_tsv`
cannot remain a same-table `GENERATED` column driven purely by
`language`, because `language` lives on `documents`, not `chunks`. The
Phase 2 migration will either (a) denormalize `language` onto `chunks` at
insert time so the generated-column expression can branch on it via a
`CASE` inside `to_tsvector(...)`, or (b) drop the generated column in favor
of computing and writing `content_tsv` explicitly during the index stage,
where the document's language is already in hand. Which of these is used
is itself a decision for that Phase 2 work, not this ADR.

## Alternatives considered

- **Guess and use `'english'` for everything (status quo).** Rejected: it's
  exactly the kind of silent, unmeasured quality degradation the eval
  harness (§10) exists to catch, and §10 explicitly requires Swahili
  questions in the golden set — shipping this without a decision risks
  discovering it only after eval numbers look mysteriously bad on Swahili
  items.
- **Install/compile a third-party Swahili FTS dictionary/configuration for
  PostgreSQL.** Rejected for v1: no well-maintained, widely-used Swahili
  `tsearch` configuration was identified, and building one is a
  linguistics effort disproportionate to v1 scope. `'simple'` is a
  pragmatic baseline; revisit if eval data shows it's insufficient.
- **Drop sparse retrieval for Swahili entirely, rely on dense-only.**
  Rejected: it would make the hybrid-retrieval comparison (§10) inconsistent
  across languages and forfeit exact-term matching (e.g. reference numbers,
  proper nouns) that sparse retrieval is good at, for no clear benefit.

## Consequences

- Phase 2's retrieval eval (§10) must report the dense/sparse/hybrid
  comparison broken out by language, not just in aggregate, so a
  `'simple'`-config regression or improvement for Swahili is visible rather
  than averaged away by the larger English-language golden set.
- Any future third language addition (ADR 0001's "add TRA/FIU/EAC with zero
  engine changes") must go through this same per-language `regconfig`
  decision — `sources.yaml` gains a source's document language(s), but the
  actual `regconfig` mapping is a small, explicit lookup in code, not
  inferred.
