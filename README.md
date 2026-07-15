# Kanuni

Kanuni (Swahili: "rule / regulation") is a production-grade Retrieval-Augmented
Generation system for asking natural-language questions about Bank of
Tanzania financial regulations and receiving cited, versioned,
confidence-gated answers — it refuses rather than guesses when it isn't
confident, and every citation links back to the exact source page.

> **Demo GIF / live demo link:** not yet recorded — both require a live
> public deployment, which needs the credentials in
> [docs/NEEDS.md](docs/NEEDS.md) (none exist in the environment that built
> this codebase). Record and link both here once `deploy.yml` has actually
> run against real infrastructure.

## Architecture

```
                     ┌─────────────┐        ┌──────────────────┐
   browser  ───────▶ │  apps/web    │──────▶ │     apps/api      │
                     │  (Next.js,   │  HTTP  │  (FastAPI)        │
                     │  Vercel)     │        │  query + admin    │
                     └─────────────┘        │  HTTP surface     │
                                             └────────┬──────────┘
                                                       │
                     ┌─────────────┐                  │ SQL / pgvector
                     │ apps/ingestion│◀─────────────────┤
                     │ (worker, Fly) │                  │
                     └──────┬───────┘                  │
                             │                          ▼
                             │                  ┌──────────────────┐
                             └─────────────────▶│ Postgres+pgvector │
                                                  │   (Supabase)     │
                                                  └──────────────────┘
```

`apps/web` never calls `apps/api` from the browser directly — its own
Next.js Route Handlers proxy every request server-side, keeping the API
key off the client (see `apps/web/src/lib/serverConfig.ts`). `apps/api`
and `apps/ingestion` are separate deployable services that share a
database, not code (ADR 0005) — the query path (`apps/api`) never blocks
on ingestion, and ingestion runs as an independent worker loop.

See [PROJECT_SPEC.md §5](PROJECT_SPEC.md#5-architecture) for the full
query and ingestion sequence diagrams, [docs/architecture.md](docs/architecture.md)
for narrative detail, [docs/data-model.md](docs/data-model.md) for the
schema, and [docs/adr/](docs/adr/) for the individual design decisions
(hybrid retrieval + RRF, bge-m3, confidence-threshold calibration,
Postgres-backed jobs, chunking strategy, API-key auth, and more).

## Key features

- **Hybrid retrieval**: dense (bge-m3 embeddings, pgvector HNSW) + sparse
  (Postgres full-text search) fused with Reciprocal Rank Fusion, then
  re-ranked with a cross-encoder (bge-reranker-v2-m3).
- **Cited, verifiable answers**: every claim traces to a `[chunk:<id>]`
  marker resolved to the source document, section, page range, and a
  direct link to that page of the original PDF — server-side validated,
  so a hallucinated citation is stripped (and an answer with zero
  surviving citations is converted to a refusal) before it reaches you.
- **Confidence-gated, not confidently wrong**: a three-tier gate
  (refuse / low-confidence / ok) means Kanuni tells you when it isn't
  sure, and points you at the nearest matching documents instead of
  guessing.
- **Point-in-time aware**: amendment and supersession relations are
  tracked (`document_relations`), so an answer can reflect that a
  regulation has since been amended rather than silently citing a
  superseded version.
- **Multilingual**: English and Swahili, including per-language
  full-text search configuration (ADR 0004).
- **A real evaluation harness, not a vibe check**: retrieval metrics
  (recall@5, recall@20, MRR, nDCG@10) compared across dense-only /
  sparse-only / hybrid / hybrid+rerank, plus answer-quality metrics
  (faithfulness via LLM-as-judge with a judge model different from the
  answer model, citation precision/recall, refusal accuracy) — see
  Evaluation below.

### Evaluation results

**Not yet populated with real numbers.** `evals/run_retrieval_eval.py`
and `evals/run_answer_eval.py` are fully implemented and produce this
table when run against a live Postgres with the corpus ingested (`make
eval`), but no Postgres or `GROQ_API_KEY` exists in the environment that
built this codebase — see `docs/PROGRESS.md`'s Phase 4 notes. Run `make
eval` and paste the resulting `evals/reports/<date>.md` table here before
citing any numbers publicly; also see `evals/golden/README.md` for why
the 62-item golden set itself is still DRAFT and needs domain-expert
review first.

| mode | recall@5 | recall@20 | MRR | nDCG@10 |
|------|---------:|----------:|----:|--------:|
| dense-only | _pending_ | _pending_ | _pending_ | _pending_ |
| sparse-only | _pending_ | _pending_ | _pending_ | _pending_ |
| hybrid | _pending_ | _pending_ | _pending_ | _pending_ |
| hybrid+rerank | _pending_ | _pending_ | _pending_ | _pending_ |

## Quickstart

```bash
make setup   # install Python (uv) and JS (bun) dependencies
cp .env.example .env   # fill in GROQ_API_KEY at minimum — see docs/NEEDS.md
make dev     # docker compose up: postgres, api, ingestion worker, web
```

Once running:

- API health: `curl http://localhost:8000/healthz`
- API readiness: `curl http://localhost:8000/readyz`
- Frontend: http://localhost:3000

`make dev` brings up an empty-but-healthy stack — see "Adding your own
corpus" below to ingest documents, or `apps/ingestion/tests/fixtures/`
for six real Bank of Tanzania documents you can ingest immediately as a
smoke test:

```bash
uv run kanuni ingest apps/ingestion/tests/fixtures \
  --source bot --manifest sources.yaml \
  --api-key <a query-scoped key — see docs/NEEDS.md>
```

## Adding your own corpus

Kanuni's document sources are pure data, not code (ADR 0001, ADR 0002):

1. Add a `sources:` entry to [sources.yaml](sources.yaml) — a source id
   (slug), issuing body, jurisdiction, and (optionally) a manifest entry
   per document for title/type/language/reference metadata. See the
   file's own header comment for the full schema.
2. Drop the PDFs in a folder.
3. `kanuni ingest <folder> --source <your-source-id> --manifest sources.yaml`
   (`apps/ingestion/src/kanuni_ingest/cli.py`) walks the folder, validates
   each file, and uploads it to the admin API — already-ingested files
   (matching SHA-256) are skipped, so the command is safely re-runnable.
4. The worker picks up newly-uploaded documents automatically (polls
   every `KANUNI_WORKER_POLL_INTERVAL_SECONDS`, default 5s) and runs them
   through extraction → chunking → embedding → indexing.

No code changes are required to add a new issuing institution or
jurisdiction — see PROJECT_SPEC.md §4.4 for the reusability requirements
this is designed around.

## API examples

```bash
# Ask a question (streams Server-Sent Events: `token` deltas, then one `done` event)
curl -N -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KANUNI_API_KEY" \
  -d '{"question": "What is the minimum core capital for a commercial bank?"}'

# Browse the document registry
curl "http://localhost:8000/v1/documents?status=in_force&doc_type=regulation" \
  -H "X-API-Key: $KANUNI_API_KEY"

# Fetch a single document's metadata
curl http://localhost:8000/v1/documents/<document-id> \
  -H "X-API-Key: $KANUNI_API_KEY"
```

The original source PDF isn't served by the API — every `POST /v1/query`
citation includes a direct `source_url` pointing at the document's public
Supabase Storage URL instead (see `ResolvedCitation` in
`apps/api/src/kanuni_api/models/query.py`).

Every error response is RFC 7807 `application/problem+json` — see
`apps/api/src/kanuni_api/exceptions.py` for the full error-code
hierarchy. See [docs/NEEDS.md](docs/NEEDS.md) for how to create an API key.

## Evaluation methodology

See [PROJECT_SPEC.md §10](PROJECT_SPEC.md#10-evaluation-harness-this-is-a-headline-feature)
for the full spec. Summary:

- **Golden set** (`evals/golden/qa.jsonl`, 62 items — **DRAFT**, see
  `evals/golden/README.md`): English + Swahili questions, point-in-time/
  amendment cases, and 12 out-of-corpus questions that must be refused.
- **Retrieval metrics** (`evals/run_retrieval_eval.py`): recall@5,
  recall@20, MRR, nDCG@10, computed separately for dense-only,
  sparse-only, hybrid, and hybrid+rerank — the comparison table is the
  actual evidence for the hybrid-retrieval architecture choice (ADR
  entries), not just an assumption.
- **Answer metrics** (`evals/run_answer_eval.py`): faithfulness
  (LLM-as-judge, judge model deliberately different from the answer
  model — grading your own answers with the model that produced them
  inflates scores), citation precision (computed directly from the raw
  vs. validated citation lists, no judge needed), refusal accuracy
  (false-answer rate on must-refuse items, false-refusal rate on
  answerable ones).
- `make eval` runs the full suite locally and writes
  `evals/reports/<date>.md`. In CI, `.github/workflows/evals.yml` runs on
  every PR touching retrieval/generation/prompts/chunking/eval code and
  posts a metrics-diff comment against the PR's base branch.

## Limitations & responsible use

Kanuni is an information retrieval tool, **not a substitute for
professional legal or regulatory advice**. Coverage is limited to
whatever has been ingested into the corpus — it will refuse rather than
fabricate an answer about topics outside it, but retrieval and
generation are automated and can make mistakes: a low-confidence banner
or a refusal both mean "verify against the cited source." Point-in-time
accuracy depends on the corpus being kept current — an amendment not yet
ingested won't be reflected in an answer about the document it amends.
For decisions with legal or financial consequences, consult a qualified
professional and verify against the primary source.

## Repository layout

See [PROJECT_SPEC.md § 3](PROJECT_SPEC.md#3-repository-structure-monorepo)
for the full monorepo layout and the rationale behind it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability disclosure policy.

## License

[MIT](LICENSE)
