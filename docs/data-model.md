# Data Model

Full DDL lives in `infra/migrations/`. This document narrates the "why"
behind the schema; PROJECT_SPEC.md §6 is the source of truth for the "what."

## documents

One row per ingested source document (a BoT circular, act, regulation,
etc.). `file_sha256` dedupes re-uploads. `status` (`in_force` |
`superseded` | `repealed` | `unknown`) drives the default retrieval filter
(§6 versioning rule): superseded/repealed documents are excluded from
retrieval unless `include_historical=true` is requested.

## document_relations

Explicit edges between documents (`supersedes` | `amends` | `refers_to`),
e.g. "Circular 4/2024 supersedes 9/2022." This is what makes the
supersession graph queryable rather than inferred at answer time.

## chunks

The retrieval unit. `content_tsv` (generated tsvector) backs sparse search;
`embedding vector(1024)` (bge-m3 dimensionality) backs dense search.
`section_ref` + `page_start`/`page_end` are what citations resolve to —
without them, an answer can't point to a specific clause. Indexed with
HNSW (embedding) and GIN (content_tsv) for the hybrid retrieval path in
§8.1.

## ingestion_jobs

Per-document stage status (`fetched` | `extracted` | `chunked` | `embedded`
| `indexed` | `failed`) plus attempt counts and structured error details.
This is what makes ingestion resumable (§4.2, §7): a crashed run resumes
from the last completed stage instead of reprocessing from scratch.

## queries

One row per answered (or refused) question: retrieved chunk IDs,
confidence, latency, token cost. Powers analytics, the eval harness (§10),
and the cost dashboard (§11).

## api_keys

Hashed (SHA-256) API keys with scopes (`query`, `ingest:admin`) and a
per-key rate limit. Keys are never stored in plaintext (§4.3).
