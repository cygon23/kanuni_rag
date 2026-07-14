# 0002. `documents.source_id` is a free-text slug, not a foreign key

## Context

`documents` needs to record which configured source (per `sources.yaml`) a
document came from. The natural relational instinct is a `sources` table
with `documents.source_id` as a foreign key. But PROJECT_SPEC.md §4.4 states
the corpus is pluggable: "adding a new document source = adding a YAML
entry in `sources.yaml` + optionally a fetcher class," and ADR 0001 commits
to zero engine changes when a new institution is added.

## Decision

`documents.source_id` is a plain `text` column holding a slug (e.g. `bot`)
that matches a key in `sources.yaml`. There is no `sources` table and no
foreign-key constraint on this column. `sources.yaml` — config, not
data — is the single source of truth for what sources exist, their issuing
body, jurisdiction, and fetch configuration.

## Alternatives considered

- **A `sources` table with a FK.** Rejected: it would require a migration
  every time a new source is registered, directly contradicting the
  "add TRA with zero engine changes" requirement from ADR 0001 — a schema
  migration is an engine change. It would also duplicate `sources.yaml`'s
  data in two places that could drift.
- **A `sources` table populated automatically from `sources.yaml` at
  startup, with the FK pointing at it.** Rejected as unnecessary complexity
  for v1: it buys referential integrity at the cost of a sync mechanism,
  for a value (`source_id`) that's already validated once, at ingestion
  time, against the loaded `sources.yaml`.

## Consequences

- Referential integrity on `source_id` is enforced at ingestion time (the
  fetch/upload path validates `source_id` against the loaded `sources.yaml`
  before writing the row), not by the database.
- Renaming a source slug in `sources.yaml` is a data migration
  (`UPDATE documents SET source_id = ...`) if historical rows must follow,
  not a schema migration — this is the intended tradeoff.
- `documents_source_id_idx` (migration 0001) still makes filtering/grouping
  by source efficient without a FK.
