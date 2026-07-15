# Progress

Tracks the autonomous execution of PROJECT_SPEC.md §14 Phases 2–6, per
CLAUDE.md's Autonomous Execution Protocol. Phases 0 and 1 are complete
(handoff summaries given in conversation, not repeated here).

---

## Phase 2 — Retrieval

### Plan

Scope: §14 Phase 2 + §8.1 (retrieval algorithm) + §2 (bge-m3, bge-reranker-v2-m3)
+ ADR 0004 (per-language tsvector — implement now, as ADR 0004 deferred to
this phase) + §6 (chunks table).

1. Migration `0002`: implement ADR 0004 — add `chunks.language` (denormalized
   from `documents.language` at insert time so the generated column can
   branch on it), regenerate `content_tsv` as
   `to_tsvector(CASE WHEN language='sw' THEN 'simple' ELSE 'english' END, content)`,
   recreate the GIN index.
2. `kanuni_ingest`: add `language` to `DocumentChunk`, populate it in the
   chunking stage from the document's language, write it in
   `chunks_repository.replace_chunks`.
3. `apps/api`: own `embedding.py` (bge-m3 provider + fake, mirrors
   `kanuni_ingest`'s per ADR 0005) and new `reranker.py`
   (bge-reranker-v2-m3 provider + fake).
4. `apps/api/retrieval/`: `dense.py`, `sparse.py`, `fusion.py` (RRF, k=60),
   `rerank.py` — all thresholds/top-k values config-driven
   (`KANUNI_DENSE_TOP_K` etc., already documented in `.env.example`).
5. `services/retrieval_service.py` orchestrating embed → dense+sparse →
   fusion → rerank.
6. `GET /v1/admin/retrieve` debug endpoint (scope `ingest:admin`, consistent
   with other `/v1/admin/*` routes) returning scored chunks.
7. A small fixture-scoped golden set (`evals/golden/fixture_qa.jsonl`,
   ~12 items against the 6 Phase 1 fixtures) — distinct from Phase 4's
   full 60-item production dataset, which doesn't exist yet.
8. `evals/run_retrieval_eval.py`: real implementation computing
   recall@5, recall@20, MRR, nDCG@10 for dense-only / sparse-only /
   hybrid / hybrid+rerank, against the fixture golden set.

Cannot be verified live here: no local Postgres/pgvector, so the eval
script's actual numbers are unverified — built and unit-tested against
mocked providers, marked "pending live verification" below.

### Completed

- Migration `0002`: `chunks.language` + per-language `content_tsv`
  (`'simple'` for `sw`, `'english'` otherwise), GIN index recreated, tested
  down path included. **Built, pending live verification** (no local
  Postgres to apply it against).
- `kanuni_ingest`: `DocumentChunk.language`, threaded through
  `chunk_document()` → `pipeline.py` → `chunks_repository.replace_chunks`.
- `apps/api`: `embedding.py` (`Bgem3EmbeddingProvider`), `reranker.py`
  (`Bgereranker`, `sentence_transformers.CrossEncoder`) — both lazy-load,
  mirroring the ingestion-side pattern (ADR 0005).
- `retrieval/{dense,sparse,fusion,rerank}.py`, `services/retrieval_service.py`,
  `GET /v1/admin/retrieve` (scope `ingest:admin`). All thresholds
  (`dense_top_k`, `sparse_top_k`, `rrf_k`, `fusion_top_k`, `rerank_top_k`)
  added to `Settings`, already documented in `.env.example` since Phase 0.
- `evals/golden/fixture_qa.jsonl` — 12 items (10 answerable across all 6
  Phase 1 fixtures + 2 out-of-corpus refusal items) for this phase's
  fixture-scale comparison; ground truth is document-level, resolved by
  the eval script computing each fixture's SHA-256 at run time (no
  dependency on ingestion-time UUIDs).
- `evals/run_retrieval_eval.py`: real dense/sparse/hybrid/hybrid+rerank
  comparison (recall@5, recall@20, MRR, nDCG@10) using real bge-m3/
  bge-reranker-v2-m3 models (§13: evals are the only place real models
  run). **Built, pending live verification** — needs a real Postgres with
  the 6 fixtures ingested, plus a bandwidth/time budget to download both
  models; neither is available in this sandbox.
- Tests: 10 new unit tests (RRF math, rerank ordering/truncation, debug
  endpoint auth + happy path) — all mocked, none load a real model.
- Found and fixed a real bug while wiring tests: `apps/api/tests/fakes.py`
  and `apps/ingestion/tests/fakes.py` shared the bare module name `fakes`;
  under a single pytest run, whichever collected first shadowed the other
  in `sys.modules`, breaking the second tree's imports. Renamed the
  api-side one to `api_fakes.py` and added a matching mypy override.

### Verification

- `ruff check` / `ruff format --check`: clean (93 source files)
- `mypy --strict`: clean (93 source files)
- `pytest`: 107 passed, 9 skipped (same 9 Phase 1 integration tests,
  correctly gated on an unavailable local Postgres)
- Frontend `lint`/`typecheck`: clean (untouched this phase)

### Open ADR candidates

- Sparse retrieval always parses the query with the `english` text-search
  config, even for Swahili questions (documented as a note in
  `sparse.py`, not yet a formal ADR) — dense retrieval (genuinely
  multilingual) compensates in the fused result; revisit if eval data
  shows this matters.
- Document-level (not chunk-level) relevance ground truth in the fixture
  golden set, and the approximated-ideal nDCG@10 — both documented inline
  in `run_retrieval_eval.py`, worth a formal ADR once Phase 4's full
  golden set exists and this method either persists or is replaced.
- `/v1/admin/retrieve` scoped `ingest:admin` rather than `query` — spec
  doesn't specify; grouped with other `/v1/admin/*` routes for consistency.

### Commit message

```
phase-2: hybrid retrieval (dense + sparse + RRF + rerank)

- Migration 0002: implements ADR 0004 (per-language chunk tsvector —
  'simple' for Swahili, 'english' otherwise)
- kanuni_ingest: DocumentChunk.language threaded through chunking,
  pipeline, and chunk persistence
- apps/api: bge-m3 query embedding + bge-reranker-v2-m3 cross-encoder
  providers (lazy-loaded, mirrors ingestion's pattern per ADR 0005)
- apps/api/retrieval/: dense (pgvector cosine), sparse (FTS ts_rank_cd),
  fusion (RRF k=60), rerank — all thresholds config-driven
- GET /v1/admin/retrieve debug endpoint (scope ingest:admin)
- evals/golden/fixture_qa.jsonl (12 items) + real
  run_retrieval_eval.py producing the dense/sparse/hybrid/hybrid+rerank
  comparison table (recall@5, recall@20, MRR, nDCG@10)
- 10 new unit tests, all mocked; fixed a cross-package test-fixture
  module-name collision (apps/api/tests/fakes.py -> api_fakes.py)

Tests: 107 passed, 9 skipped (unchanged skip set — no local Postgres).
ruff, mypy --strict, frontend lint/typecheck: all clean.

Built, pending live verification: migration 0002 (needs a real Postgres
to apply), run_retrieval_eval.py's actual metrics (needs a real Postgres
with the Phase 1 fixtures ingested, plus bge-m3/bge-reranker-v2-m3
downloaded — see docs/PROGRESS.md).
```

---

## Phase 3 — Generation & citations

### Plan

Scope: §14 Phase 3 + §8.2 (confidence gate) + §8.3 (generation & citation
contract) + §8.4 (API surface) + §2 (Groq) + §4.2 (external-call resilience).

1. `generation/llm_client.py`: `LLMProvider` protocol (streaming text
   deltas), `GroqLLMProvider` (real, httpx SSE against Groq's
   OpenAI-compatible endpoint), `FallbackLLMProvider` (tries a primary,
   falls back to a secondary on `ProviderTimeoutError`/
   `ProviderRateLimitError` if one is configured — §2's "fallback slot").
2. `generation/prompts/answer_v1.md`: versioned prompt file, never inline.
3. `generation/citation.py`: parses `[chunk:<id>]` markers, strips invalid
   ones, computes `citation_density`, converts zero-valid-citation answers
   to a refusal (§8.3).
4. `generation/confidence.py`: three-tier gate (`refuse` / `low` / `ok`)
   from `KANUNI_CONFIDENCE_REFUSE_THRESHOLD` / `_CAUTION_THRESHOLD`
   (already in `.env.example` since Phase 0).
5. `services/query_service.py`: retrieve → gate → (refusal | generate →
   validate citations → assemble metadata) → log to `queries`.
6. `POST /v1/query` (scope `query`), SSE via `sse-starlette`.
7. `db/queries_repository.py`: log question, retrieved chunk ids,
   confidence, latency, token cost, answered.
8. `GROQ_API_KEY` appended to `docs/NEEDS.md`.

Deliberate scope line per the task's Phase 3 directive: real Groq calls
only inside `GroqLLMProvider`; every test uses a fake implementing
`LLMProvider`. Cannot be verified live here (no `GROQ_API_KEY`) — the
provider is built and unit-tested against the fake, marked "pending live
verification" below.

### Completed

- `generation/llm_client.py`: `LLMProvider` protocol (streaming
  `GenerationChunk`s), `GroqLLMProvider` (real, httpx SSE parsing of
  Groq's OpenAI-compatible endpoint, `stream_options.include_usage` for
  token counts), `FallbackLLMProvider` (transparent passthrough today —
  no second concrete provider exists to fall back to yet; documented
  limitation: only cleanly handles pre-first-token failures).
- `generation/prompts/answer_v1.md` + `prompt_loader.py`: the §8.3 tagged
  context block (`[chunk:<id>] (title, reference_number, section_ref,
  status)`), never an inline string.
- `generation/citation.py`: parses `[chunk:<id>]`, strips hallucinated
  ids, computes `citation_density = valid citations / sentence count`
  (a defined-here metric — spec doesn't specify the exact formula),
  reports `has_valid_citations` for the zero-citation → refusal rule.
- `generation/confidence.py`: the three-tier gate, boundary-tested.
- `services/query_service.py`: full orchestration — refuses immediately
  on low confidence (no LLM call), otherwise generates, validates
  citations (converting to refusal if none survive), builds resolved
  citations + up to 3 nearest-document pointers on refusal, logs every
  query (`queries` table), and flags (logs only, never blocks) answers
  citing a non-`in_force` document without disclosure language.
- `POST /v1/query` (scope `query`, SSE via `sse-starlette`).
- `db/queries_repository.py`; `Settings.groq_api_key` reads the bare
  `GROQ_API_KEY` (provider convention, not `KANUNI_`-prefixed — resolves
  the naming ambiguity flagged back in the Phase 1 handoff).
- `GROQ_API_KEY` appended to `docs/NEEDS.md` with setup steps.
- Tests: 24 new (7 citation, 9 confidence-boundary, 5 query-service
  orchestration, 3 route-level auth/validation) — all mocked via
  `FakeLLMProvider`/`FakeEmbeddingProvider`/`FakeRerankerProvider`.

### Verification

- `ruff check` / `ruff format --check`: clean (105 source files)
- `mypy --strict`: clean (105 source files)
- `pytest`: 131 passed, 9 skipped (same 9 — unavailable local Postgres)
- Frontend `lint`/`typecheck`: clean (untouched this phase)

### Open ADR candidates

- `citation_density` formula (valid citations ÷ sentence count) — spec
  requires computing and logging it but doesn't define it; worth
  formalizing once eval data shows whether it's a useful signal.
- Illustrative per-token cost constants in `query_service.py` are *not*
  Groq's real published rates — placeholder until real pricing is
  sourced; cost figures should not be cited as accurate before that.
- Undisclosed-historical-citation detection is a keyword heuristic
  (logs only, never blocks) — worth revisiting once real answers exist
  to check false-positive/negative rates.

### Commit message

```
phase-3: generation, citations, confidence gate, POST /v1/query

- generation/llm_client.py: LLMProvider protocol, GroqLLMProvider
  (streaming SSE via httpx), FallbackLLMProvider (fallback slot,
  currently a passthrough — no second provider implemented yet)
- generation/prompts/answer_v1.md + prompt_loader.py: versioned system
  prompt with the §8.3 tagged context block
- generation/citation.py: strips hallucinated [chunk:<id>] citations,
  computes citation_density, signals refusal on zero valid citations
- generation/confidence.py: refuse/low/ok three-tier gate
- services/query_service.py: full orchestration (retrieve -> gate ->
  generate -> validate -> log), refusal pointers, undisclosed-
  historical-citation logging
- POST /v1/query (scope query), SSE streaming
- db/queries_repository.py; Settings.groq_api_key reads bare
  GROQ_API_KEY (not KANUNI_-prefixed, matching the provider's own
  convention)
- GROQ_API_KEY documented in docs/NEEDS.md
- 24 new tests, all mocked (FakeLLMProvider et al.)

Tests: 131 passed, 9 skipped (unchanged skip set).
ruff, mypy --strict, frontend lint/typecheck: all clean.

Built, pending live verification: GroqLLMProvider's actual streaming
behavior and citation quality against a real model (needs GROQ_API_KEY
— see docs/NEEDS.md).
```

---

## Phase 4 — Evaluation harness

### Plan

Scope: §14 Phase 4 + §10 (evaluation harness) + the task's explicit Phase 4
directive (draft dataset, clearly marked, refusal items genuinely absent
from the corpus).

1. `evals/golden/qa.jsonl`: 60+ items, hand-derived from the real text of
   the 6 Phase 1 fixtures (not fabricated) — English + Swahili questions,
   point-in-time/amendment cases (the 2014/2023 licensing pair), and 12
   out-of-corpus must-refuse items (tax/TRA, EAC customs, other
   institutions — topics genuinely outside the BoT corpus). Explicitly
   headed as DRAFT, pending domain-expert review before any public citation.
2. Extend `evals/run_retrieval_eval.py` to run against the full dataset
   (not just `fixture_qa.jsonl`, which stays as the small Phase 2 smoke set).
3. `evals/run_answer_eval.py`: faithfulness (LLM-as-judge, judge model ≠
   answer model), citation precision/recall, refusal accuracy (false-answer
   rate on must-refuse items, false-refusal rate on answerable items) —
   real implementation calling the real query path + a real judge model
   (§13: evals are the only place real models run).
4. `evals/report.py`: writes `evals/reports/<date>.md`.
5. `.github/workflows/evals.yml`: path-filtered (retrieval/, generation/,
   prompts/, chunking, eval code), posts a metrics-diff PR comment,
   configurable regression threshold.

Cannot be verified live here: no Postgres, no GROQ_API_KEY, no judge-model
budget. Built and structured correctly; marked "pending live verification."

### Completed

- `evals/golden/qa.jsonl`: 62 items — 12 licensing (2014), 4 amendment
  (2022/2023), 3 point-in-time (does the 2022 amendment change today's
  answer), 12 capital adequacy, 10 electronic money, 6 Swahili
  (`bot-2019-huduma-ndogo-swahili.pdf` — real Kanuni za Matumizi ya Fedha
  za Kigeni, 2025 text), 3 scanned forex, 12 out-of-corpus refusals (TRA/
  tax, EAC customs, other regulators/jurisdictions, real-time data,
  unrelated law — none reference BoT regulatory content). Every figure
  (gazette numbers, capital thresholds, section numbers, Swahili text) was
  read directly off the fixture PDFs, not invented. Two items (gd-039,
  gd-040) deliberately probe metadata that's genuinely blank on the source
  PDF, to check the system says "not available" instead of guessing.
  `evals/golden/README.md` documents the DRAFT status and the exact
  domain-expert review steps required before any public citation, per the
  task's explicit Phase 4 directive.
- `evals/run_retrieval_eval.py`: `--golden` flag (defaults to the small
  Phase 2 `fixture_qa.jsonl`; `--golden golden/qa.jsonl` runs the full
  draft set) and `--output` flag (writes metrics as JSON for `report.py`).
- `evals/run_answer_eval.py`: real implementation. Refusal accuracy
  (false-answer / false-refusal rate) computed directly from `answered`
  vs. `must_refuse` — no judge needed. Citation precision computed
  directly from the raw streamed answer text vs. the server's
  post-validation citation list (chunk ids the LLM attempted to cite,
  valid or hallucinated, vs. the ones that survived `validate_citations`)
  — also no judge needed. Faithfulness and ideal-answer-point coverage
  *are* judged, by a second, different, smaller Groq model
  (`Settings.eval_judge_llm_model = "llama-3.1-8b-instant"`, vs.
  `Settings.llm_model = "llama-3.3-70b-versatile"` for the answer itself)
  — grading your own answers with the model that produced them inflates
  scores, so this is a deliberate, documented choice, not an oversight.
- `evals/prepare_eval_corpus.py`: seeds and fully ingests the 6 Phase 1
  fixtures for CI, mirroring the Phase 1 integration test's seeding
  pattern rather than the HTTP admin-upload API (no long-lived worker in
  a one-shot CI job). Uses the real `Bgem3EmbeddingProvider` and, for the
  scanned fixture, real `TesseractOCREngine` — both genuinely affect
  retrieval quality. Uses a no-op metadata-extraction stand-in rather than
  `GroqMetadataExtractionProvider`: `versioning.py` resolves
  `reference_number` and `amends`/`supersedes` relations via regex on the
  source text, never from the LLM call, so a real Groq call here would add
  cost and a new CI failure mode without changing any eval-relevant
  output. Titles/reference numbers are seeded directly, matching what
  `qa.jsonl`'s questions assume.
- `evals/report.py`: renders `evals/reports/<date>.md` from whichever of
  the retrieval/answer result JSON files are available (either or both
  may be missing — e.g. a fork PR with no `GROQ_API_KEY` still gets a
  retrieval-only report, never a hard failure). Renders a regression-
  diff table against baseline result JSON when supplied, threshold
  configurable via `--threshold` (workflow input in CI, default 0.02).
- `.github/workflows/evals.yml`: path-filtered on
  `apps/api/src/kanuni_api/{retrieval,generation,embedding.py,reranker.py}`,
  `apps/ingestion/src/kanuni_ingest/stages/chunk.py`, and `evals/**`.
  Spins up `pgvector/pgvector:pg15`, runs migrations, installs tesseract,
  ingests the corpus, runs both eval scripts, renders the report, and
  posts it as a sticky PR comment. Baseline for the regression diff is
  downloaded from the most recent successful run on the PR's base branch
  via `dawidd6/action-download-artifact` (no baseline file is committed —
  that would mean fabricating eval numbers before any real run has
  happened; the first run on a fresh base branch has no baseline and the
  report says so). The answer-eval step is individually guarded on
  `secrets.GROQ_API_KEY != ''` so a fork PR (no secrets access) still
  produces a retrieval-only comment instead of failing the job.
- `docs/NEEDS.md`: split the Groq section into "generation" (`GROQ_API_KEY`,
  also used by the eval judge) and "ingestion metadata extraction"
  (`KANUNI_GROQ_API_KEY`, a genuine Phase 1 production need that hadn't
  been documented yet since `NEEDS.md` didn't exist until this session) —
  the latter noted as *not* required for `prepare_eval_corpus.py` itself.
  Also documented the `GROQ_API_KEY` GitHub Actions repository secret
  `evals.yml` depends on.
- `Settings.eval_judge_llm_model` added (`apps/api/src/kanuni_api/config.py`).

### Verification

- `ruff check` / `ruff format --check`: clean (106 source files)
- `mypy --strict`: clean (106 source files)
- `pytest`: 131 passed, 9 skipped (unchanged skip set — unavailable local
  Postgres; no new tests this phase, since eval scripts are themselves
  the §13 exception where real models run and are explicitly out of
  pytest's scope)
- Frontend `lint`/`typecheck`/`format:check`: clean (untouched this phase)
- `evals/report.py` manually smoke-tested end-to-end against fabricated
  JSON metrics (not committed) — table rendering, missing-section
  handling, and the diff section all verified to produce correct
  markdown output
- `.github/workflows/evals.yml` YAML-syntax-validated with `yaml.safe_load`

Cannot be verified live: `prepare_eval_corpus.py`'s actual ingestion
(needs Postgres + tesseract + bge-m3 download), `run_retrieval_eval.py`'s
and `run_answer_eval.py`'s actual metrics against `qa.jsonl` (needs
Postgres, `GROQ_API_KEY`, and both a generation and a judge model
download/call budget), and the `evals.yml` workflow itself (needs a real
GitHub Actions run — the YAML is syntactically valid and structurally
mirrors `ci.yml`'s conventions, but its actual execution is unverified).
All marked "built, pending live verification."

### Open ADR candidates

- Citation-precision and faithfulness/ideal-point-coverage are computed
  at different rigor levels (the former is a direct, deterministic
  computation from server output; the latter is LLM-judged and therefore
  approximate) — worth a formal ADR once real eval runs show whether the
  judge's scores are stable/trustworthy enough to gate CI on, versus
  informational-only.
- `evals/prepare_eval_corpus.py` re-derives the same seeding pattern as
  `apps/ingestion/tests/integration/test_full_ingestion.py`'s
  `_seed_document` helper rather than sharing code with it (the test
  helper lives in a test module, not something eval scripts should import
  from) — worth extracting a small shared helper into the `kanuni_ingest`
  package itself if a third caller ever needs the same pattern.
- The regression-diff baseline strategy (download the previous run's
  artifact from the PR's base branch, no committed baseline file) means
  the first eval run after this phase merges has nothing to diff against,
  and any run on a branch whose base never had a successful `evals.yml`
  run also gets no diff — acceptable for now, but worth revisiting once
  there's real historical data to decide if a periodic scheduled run
  against `main` (to keep a fresher baseline) is worth the added Groq
  cost.

### Commit message

```
phase-4: evaluation harness (golden set, retrieval + answer evals, CI)

- evals/golden/qa.jsonl: 62-item DRAFT golden set derived from the real
  text of the 6 Phase 1 fixtures (English + Swahili, point-in-time/
  amendment cases, 12 out-of-corpus must-refuse items) — clearly marked
  DRAFT pending domain-expert review before public citation
  (evals/golden/README.md documents the required review steps)
- run_retrieval_eval.py: --golden and --output flags, now runnable
  against the full draft set as well as the Phase 2 smoke set
- run_answer_eval.py: real implementation — refusal accuracy and
  citation precision computed directly (no judge needed); faithfulness
  and ideal-point coverage judged by a second, smaller Groq model
  (Settings.eval_judge_llm_model), deliberately different from the
  answer model
- prepare_eval_corpus.py: seeds + fully ingests the 6 fixtures for CI
  with real embeddings/OCR, no-op metadata extraction (regex handles
  what evals need; see module docstring)
- report.py: renders evals/reports/<date>.md, handles missing sections,
  renders a threshold-configurable regression diff against a baseline
- .github/workflows/evals.yml: path-filtered CI job, Postgres +
  pgvector service, sticky PR comment, baseline diffing via the
  previous base-branch run's artifact, answer-eval gracefully skipped
  (not failed) without GROQ_API_KEY (fork PRs)
- docs/NEEDS.md: split Groq section into generation vs. ingestion
  metadata extraction (KANUNI_GROQ_API_KEY, a real Phase 1 need not
  previously documented); documented the GROQ_API_KEY Actions secret
- Settings.eval_judge_llm_model added

Tests: 131 passed, 9 skipped (unchanged — no new tests; eval scripts are
themselves the §13 real-model exception, outside pytest's scope).
ruff, mypy --strict, frontend lint/typecheck/format: all clean.

Built, pending live verification: prepare_eval_corpus.py's ingestion,
both eval scripts' actual metrics against qa.jsonl, and evals.yml's
actual CI execution — all need Postgres + GROQ_API_KEY + model downloads
unavailable in this sandbox (see docs/NEEDS.md).
```

---

## Phase 5 — Frontend

### Plan

Scope: §14 Phase 5 + §9 (frontend spec) in full, against the local API
(task directive overrides §14's "deployed on Vercel against staging"
deliverable — no cloud credentials exist here; Vercel deploy config and
steps are Phase 6/`docs/NEEDS.md` concerns).

1. **Architecture decision:** the browser never calls the Kanuni API
   directly or holds an API key. `apps/web`'s own Next.js Route Handlers
   (`/api/query`, `/api/documents`, `/api/documents/[id]`,
   `/api/documents/[id]/file`) proxy to `KANUNI_API_BASE_URL` with
   `KANUNI_API_KEY` attached server-side (both server-only env vars, never
   `NEXT_PUBLIC_*`) — the only way to keep the API key off the client
   bundle given the API's existing API-key-scope auth model (§4.3), and it
   incidentally sidesteps CORS entirely (same-origin from the browser's
   perspective). `/api/query` streams the upstream SSE response straight
   through via a passthrough `ReadableStream`.
2. **Gap found while reading the API for this proxy:** nothing served the
   raw PDF bytes §9 requires linking to ("a link to the source PDF page").
   Added `GET /v1/documents/{id}/file` (scope `query`, same auth pattern
   as the rest of `/v1/documents/*`) — a small, additive, read-only
   endpoint filling a capability §9 already implies, not a new public API
   shape beyond the spec, so built directly rather than pausing to ask
   per the protocol's question rule. `#page=N` on the returned URL relies
   on standard browser PDF-viewer fragment support, not a server feature.
3. Shared layout: top nav (Ask / Documents / About), dark mode via
   Tailwind's existing `media` strategy (already configured Phase 0 — no
   manual toggle needed to satisfy §9's "dark mode" line).
4. **Ask page:** input + submit, SSE consumption via `fetch` + a manual
   `ReadableStream` reader (browsers' native `EventSource` can't send the
   `POST` body or custom flow this needs), inline `[chunk:<id>]` citation
   chips rendered from the streamed text, a slide-over side panel (chunk
   text, document metadata, page range, "open source PDF" link) triggered
   per chip, a confidence banner for `low`, a distinct refusal state
   showing nearest-document pointers, recent-questions list in
   `localStorage` only (never sent anywhere), loading/skeleton state, and
   distinguished error states (401/403 "check your API key", 429
   "rate-limited, retry in Ns", 5xx "server error", network failure) —
   no bare spinners per §9.
5. **Documents page:** table/list of `GET /v1/documents`, filters for
   `status` and `doc_type` reflected in the URL query string (shareable/
   bookmarkable), pagination, empty and loading states.
6. **About page:** static — what this is, corpus coverage (reads from
   `GET /v1/documents` for a live count), limitations and a "not legal
   advice" responsible-use note (§16 will reuse this note verbatim in the
   README).
7. Accessibility: semantic landmarks, visible focus states, aria-live on
   the streaming answer region and confidence/refusal banners, keyboard-
   operable citation chips and side panel (focus trap + Escape to close).

No new frontend test framework is introduced this phase — `apps/web`'s
`package.json` already has `"test": "echo ..."` as an explicit Phase 5
placeholder (Phase 0), and PROJECT_SPEC.md's testing requirements (§13)
are scoped to Python; component/e2e frontend tests aren't specified as a
gate here. VERIFY for this phase is eslint + tsc + prettier, matching
`ci.yml`'s existing `lint-web` job exactly.

Cannot be verified live here: no running Kanuni API (no local Postgres),
so the proxy routes and pages are built and manually reasoned through
against the API's actual response shapes, but never exercised against a
live backend — marked "pending live verification" below.

### Completed

- **Real bug found and fixed while building the SSE client**: `POST
  /v1/query`'s `done` event, as shipped in Phase 3, serialized invalid
  JSON on the wire. `EventSourceResponse`'s default `ServerSentEvent`
  encodes a dict `data` value with plain `str()`, not `json.dumps` (only
  `JSONServerSentEvent` does the latter) — so `{"event": "done", "data":
  metadata.model_dump(mode="json")}` produced a Python dict repr
  (single-quoted keys, `True`/`None`) instead of JSON. Phase 3's tests
  never caught this because they call `run_query()` directly as an async
  generator and inspect the dict before SSE encoding — the bug only shows
  up in the actual wire bytes. Fixed by having `run_query` yield
  `metadata.model_dump_json()` (a pre-serialized string) instead; added a
  route-level regression test
  (`test_query_streams_sse_with_a_json_encoded_done_event` in
  `apps/api/tests/routes/test_query.py`) that exercises the real
  `EventSourceResponse` encoding path and would have caught this. Updated
  `test_query_service.py`'s existing assertions to parse `data` as JSON
  (via a new `_done_data` helper) to match the corrected contract.
- **Two small, additive API surface changes**, both filling capabilities
  §9 explicitly requires and neither changing existing behavior — decided
  and built directly per the protocol's "small reversible choices: decide,
  record, continue" rule rather than pausing to ask:
  - `GET /v1/documents/{id}/file` (scope `query`): streams the original
    PDF bytes. Nothing served raw source files before this — needed for
    §9's "a link to the source PDF page." Added `DocumentStorage.read()`
    (mirroring `kanuni_ingest`'s copy, per ADR 0005) and
    `documents_repository.find_storage_path()`.
  - `ResolvedCitation.content: str` (in `models/query.py`, populated from
    `chunk.content` in `query_service.py`): §9 requires the citation side
    panel to show "the exact chunk text" — without this the frontend
    would need a second round trip (or a new endpoint) per citation.
  Both changes are purely additive (new field, new route); no existing
  response shape lost fields or changed types.
- `packages/shared`: wired up the OpenAPI codegen the Phase 0 scaffolding
  anticipated (`README.md`'s "populated starting Phase 5"). Added
  `apps/api/scripts/export_openapi_schema.py` — calls `create_app()` and
  `.openapi()` directly, no running server or database needed, since
  FastAPI derives the schema from the registered route table alone.
  `openapi-typescript` generates `packages/shared/src/generated/api.ts`;
  `make openapi` runs both steps. `index.ts` re-exports the
  OpenAPI-derived types (`DocumentSummary`, `QueryRequest`, etc.) under
  friendlier names, plus three hand-maintained type groups that FastAPI's
  schema generator can't see: `POST /v1/query`'s SSE payload
  (`QueryResultMetadata`, `ResolvedCitation`, `DocumentPointer` —
  `EventSourceResponse` isn't introspectable) and error responses
  (`ProblemDetails` — built as a raw dict in `error_handler.py`, not
  through a `response_model`). Both are commented with why they're
  hand-maintained and what to keep in sync. Added `typescript` as a
  direct devDependency of `packages/shared` (it had none — relied on
  hoisting from `apps/web`, which broke `packages/shared`'s own
  `typecheck` script run standalone) and `@kanuni/shared` as a workspace
  dependency of `apps/web`.
- **Proxy architecture**: `apps/web`'s own Route Handlers
  (`src/app/api/{query,documents,documents/[id],documents/[id]/file}/route.ts`)
  are the only thing that ever calls the Kanuni API — `lib/serverConfig.ts`
  attaches `KANUNI_API_KEY` server-side (via the `server-only` package, so
  importing it from a Client Component is a build error, not a silent
  leak). The browser only ever talks to `apps/web` itself, same-origin.
  Each proxy route catches upstream connection failures explicitly and
  returns a well-formed `application/problem+json`-shaped 502 (via
  `upstreamUnavailableResponse()`) instead of letting Next.js's default
  handler produce an opaque empty-bodied 500 — verified by running the
  dev server against an intentionally-unreachable `KANUNI_API_BASE_URL`
  (see Verification below).
- **Ask page** (`/`, `components/AskExperience.tsx`): question textarea
  (Enter submits, Shift+Enter newlines), SSE consumption via
  `lib/streamQuery.ts` (a hand-rolled frame parser — `EventSource` can't
  send a POST body, so the native browser API doesn't work here),
  `lib/citations.ts` splits streamed text on `[chunk:<id>]` markers
  (regex kept in sync with `citation.py`'s pattern via a comment) into
  clickable `CitationChip`s numbered by first-appearance order,
  `ChunkSidePanel` (focus-trapped, Escape-to-close, shows chunk text +
  document metadata + page range + source-PDF link with a `#page=N`
  fragment), `ConfidenceBanner` for `low` confidence, `RefusalState`
  showing nearest-document pointers, `RecentQuestions` (localStorage
  only, per §9), a skeleton while waiting for the first token, and
  `ErrorState` distinguishing 401/403, 429, 5xx, and network failures
  (`lib/streamQuery.ts`'s `QueryRequestError` carries the parsed
  `ProblemDetails`).
- **Documents page** (`/documents`, `components/DocumentsExperience.tsx`):
  status/type filters reflected in the URL query string (shareable,
  survives reload), loading skeleton, empty state, error state. Data
  fetching is a nested async function inside the effect body (not
  inlined) so every `setState` call happens after an `await`, never
  synchronously as the effect runs — required to satisfy
  `eslint-plugin-react-hooks`'s `set-state-in-effect` rule, which is
  enabled by default in this Next.js 16 / React 19 setup.
- **About page** (`/about`, Server Component): static copy on what
  Kanuni is and its limitations, a live document count (server-fetched,
  `cache: "no-store"` so it's excluded from static prerendering and the
  fetch failure path — tested — degrades to "Document count is
  unavailable right now" rather than crashing the page), and the
  "not legal advice" responsible-use note — worded so §16's README can
  reuse it verbatim.
- `lib/useRecentQuestions.ts`: rewritten from an initial `useEffect` +
  `setState` implementation (also flagged by `set-state-in-effect`) to
  `useSyncExternalStore` — the actually-correct React primitive for
  subscribing to state that lives outside React (localStorage), and
  incidentally also fixes a real (minor) issue the effect-based version
  had: no cross-tab sync. Listens for the `storage` event.
  `evals/golden/README.md`-style honesty note not needed here, but the
  module docstring explains the store-cache-invalidation logic.
- Shared layout (`app/layout.tsx`): top nav (`components/Nav.tsx`,
  active-link styling via `usePathname`), skip-to-content link, dark
  mode via Tailwind's pre-existing `media` strategy (no manual toggle
  needed — §9's requirement is satisfied by the Phase 0 config already
  being correct).
- Accessibility: semantic `<nav>`/`<main>`/`<dialog role>` landmarks,
  visible `focus-visible` rings throughout, `aria-live="polite"` on the
  streaming answer region and the confidence/refusal banners,
  `aria-label`s on citation chips describing the citation's document and
  section, a real focus trap + Escape handling in `ChunkSidePanel`, and a
  skip-to-content link in the root layout.
- Manually verified end-to-end against a live `next dev` server with
  `KANUNI_API_BASE_URL` pointed at an unreachable address (no local
  Postgres/API exists in this sandbox) — see Verification below for what
  that confirmed and what remains genuinely unverified.

### Verification

- `bun run --filter kanuni-web lint` / `typecheck` / `format:check`:
  clean, matching `ci.yml`'s `lint-web` job exactly
- `bun run --filter @kanuni/shared typecheck`: clean
- `KANUNI_API_KEY=<dummy> bun run build` (production build, Turbopack):
  succeeds; route table confirms the expected static/dynamic split (`/`
  and `/documents` static-shell, `/about` and all `/api/*` routes
  dynamic — correct, since `/about` and the proxies use `cache:
  "no-store"` / are Route Handlers)
- Started `next dev` with `KANUNI_API_BASE_URL=http://localhost:1`
  (guaranteed-unreachable) and `curl`ed every route:
  - `GET /`, `/documents`, `/about` all return 200 and render (the About
    page's live document-count fetch fails and falls back to its
    "unavailable" copy, as designed, rather than crashing the page)
  - `GET /api/documents` and `POST /api/query` both return a
    well-formed 502 `application/problem+json` body via
    `upstreamUnavailableResponse()`, confirming the proxy error path
    works end-to-end at the HTTP level (this is as close to "used the
    feature in a browser" as this sandbox allows — no browser tool is
    available, and no live backend exists to exercise the actual
    question-answering path)
- Backend changes from this phase (the SSE JSON fix, the two new
  `ResolvedCitation.content` / `GET /v1/documents/{id}/file` additions)
  re-ran through the full Python gate: `ruff check` / `ruff format
  --check`: clean (107 source files); `mypy --strict`: clean (107 source
  files); `pytest`: 134 passed, 9 skipped (unchanged skip set — up from
  131 passed in Phase 4, +3 for the new `GET .../file` tests and the SSE
  regression test)

Cannot be verified live: the actual Ask-page question-answering flow
against a real backend (streaming tokens, real citations, real
confidence gating) — needs Postgres + the 6 fixtures ingested +
`GROQ_API_KEY`, none available here. No browser tool exists in this
sandbox either, so even with a live backend, "opened it in a browser"
verification would still require the maintainer. Marked "built, pending
live verification."

### Open ADR candidates

- The SSE `data`-must-be-a-pre-serialized-JSON-string constraint
  (`ServerSentEvent` vs. `JSONServerSentEvent`) is easy to reintroduce by
  accident in a future SSE-emitting endpoint — worth either a short ADR
  documenting the gotcha, or switching `query.py` to construct
  `JSONServerSentEvent` objects explicitly instead of relying on plain
  dicts, so the constraint is enforced by the type rather than by
  convention + a comment.
- `apps/web` proxies every API call rather than letting the browser call
  `apps/api` directly with CORS — a deliberate, low-risk default given
  the API's key-based auth model, but worth confirming still holds once
  a real deployment topology (Vercel + Fly.io, Phase 6) is in place;
  Vercel's own edge/serverless limits (function duration, streaming
  support) could affect whether the SSE passthrough in
  `app/api/query/route.ts` behaves identically in production.
- No frontend test framework was introduced (component tests, Playwright,
  etc.) — PROJECT_SPEC.md §13's testing requirements are scoped to
  Python, and `apps/web/package.json`'s `test` script has been an
  explicit "not yet" placeholder since Phase 0, but a project this far
  along with a headline interactive feature (streaming answers with
  citations) may want at least a handful of component/e2e tests before
  public launch — worth a maintainer decision, not made here since it
  wasn't blocking and wasn't asked for.
- `include_historical` (a real `QueryRequest` field) isn't exposed in the
  Ask page UI — deliberately deferred to keep the interface uncluttered
  per §9's "no clutter" instruction; revisit if users need to ask about
  superseded/repealed documents directly.
- **No API-key issuing endpoint exists.** Discovered while writing
  `docs/NEEDS.md`'s setup steps for `apps/web`'s own key: every
  `/v1/admin/*` route (the only place that could plausibly create a key)
  itself requires an already-valid `ingest:admin`-scoped key — a
  chicken-and-egg gap that traces back to Phase 0/1's auth design. The
  only way to create the *first* key is a direct database insert (steps
  given in `docs/NEEDS.md`). Not fixed here (it's an API-shape decision —
  a new admin endpoint, or a CLI/migration-time bootstrap script — outside
  this phase's scope and arguably worth a maintainer decision on the
  right shape), but flagged because it will block the maintainer at setup
  time for both `KANUNI_ADMIN_API_KEY` (Phase 1) and this phase's
  `KANUNI_API_KEY`.

### Commit message

```
phase-5: frontend (Ask, Documents, About) against the local API

- Fixed a real bug found while building the SSE client: POST /v1/query's
  `done` event serialized invalid JSON on the wire (EventSourceResponse's
  default ServerSentEvent uses str(), not json.dumps, for dict data) —
  run_query now yields a pre-serialized JSON string; added a route-level
  regression test exercising the real encoding path
- apps/api: GET /v1/documents/{id}/file (streams the source PDF) and
  ResolvedCitation.content (chunk text in the query response) — both
  additive, filling capabilities §9 requires; DocumentStorage.read()
  added to match kanuni_ingest's copy
- packages/shared: wired up OpenAPI codegen (apps/api/scripts/
  export_openapi_schema.py + openapi-typescript, `make openapi`) plus
  hand-maintained types for the SSE payload and RFC 7807 error shape
  (neither visible to FastAPI's schema generator)
- apps/web: Route Handler proxies (app/api/*) keep KANUNI_API_KEY
  server-side only (server-only package enforces this at build time);
  each proxy returns a well-formed 502 problem-details body on upstream
  failure instead of an opaque 500
- Ask page: streaming answer, inline citation chips, focus-trapped chunk
  side panel with a source-PDF deep link, confidence banner, refusal
  state with nearest-document pointers, recent questions (localStorage,
  via useSyncExternalStore), full loading/error states
- Documents page: status/type filters in the URL, loading/empty/error
  states
- About page: corpus coverage (live count), limitations, "not legal
  advice" note (worded for verbatim reuse in the README)
- Accessibility: focus-visible rings, aria-live regions, a real focus
  trap + Escape handling in the side panel, skip-to-content link
- Fixed two eslint-plugin-react-hooks set-state-in-effect violations
  (DocumentsExperience's fetch effect, useRecentQuestions — rewritten
  onto useSyncExternalStore, the correct primitive for this)

Tests: Python 134 passed, 9 skipped (+3 vs. Phase 4: two GET .../file
tests, one SSE-encoding regression test). ruff, mypy --strict, frontend
lint/typecheck/format: all clean. Verified end-to-end against a live
`next dev` server with an intentionally-unreachable API — all pages
render, all proxy error paths return well-formed JSON.

Built, pending live verification: the actual Ask-page question-answering
flow against a real backend needs Postgres + ingested fixtures +
GROQ_API_KEY (see docs/NEEDS.md); no browser tool exists in this sandbox
either.
```

---

## Phase 6 — Ship & harden

### Plan

Scope: §14 Phase 6 + §11 (observability & ops) + §12 (CI/CD) + §16
(README) + the task's explicit Phase 6 directive (deploy.yml, fly.toml,
k6 script, runbook + README finalized, everything else documented in
docs/NEEDS.md with exact commands since no cloud credentials exist here).

1. **Sentry wiring** (§11: "Sentry SDK in API, worker, and frontend, with
   release tagging from git SHA") — `sentry-sdk` in `apps/api` and
   `apps/ingestion` (`telemetry/sentry.py` in each, a blank DSN disables
   the SDK so no if-configured branching is needed anywhere), `@sentry/
   nextjs` in `apps/web` (`instrumentation.ts` + `instrumentation-
   client.ts`, Next.js's native hooks). `Settings.release_sha` /
   `NEXT_PUBLIC_RELEASE_SHA` carry the deployed commit SHA, set by
   `deploy.yml`. Explicit `capture_exception` calls added where an
   exception is caught and converted to a normal response/log line rather
   than left to propagate (`error_handler.py`'s catch-all,
   `pipeline.py`'s per-document failure path) — Sentry's automatic
   capture only sees exceptions that actually propagate.
2. **Docker/compose reconciliation**: `apps/api/Dockerfile` currently
   bakes in `--reload` (dev-only); split into a production-ready
   Dockerfile default with dev's `--reload` moved to a `command:`
   override in `docker-compose.yml`, so the same image Fly.io deploys is
   what `make dev` runs (minus the override). Also found and fixed a
   stale/dead `NEXT_PUBLIC_API_URL` in `docker-compose.yml`'s `web`
   service, left over from before Phase 5's proxy-architecture decision
   (apps/web never reads that variable) — replaced with
   `KANUNI_API_BASE_URL`/`KANUNI_API_KEY` pointed at the `api` service, so
   `make dev` actually works end-to-end.
3. **`fly.toml`** (root, apps/api) + **`fly.staging.toml`**: two Fly app
   configs (`kanuni-api`, `kanuni-api-staging`) sharing the same
   Dockerfile, `[deploy] release_command` running dbmate migrations
   pre-deploy (§12: "migrations run automatically pre-deploy"),
   `[[services.http_checks]]` against `/readyz`.
4. **`.github/workflows/deploy.yml`** (merge to main, per §12): build via
   `flyctl deploy --remote-only` (Fly's own registry — no separate
   build-and-push step needed) → deploy staging → smoke test (`/readyz` +
   one canned `/v1/query` call asserting a citation is returned) →
   `environment: production` (manual approval gate — a required-reviewers
   GitHub Environment the maintainer configures, documented in
   docs/NEEDS.md) → deploy prod → Sentry release via
   `getsentry/action-release`, tagged with `github.sha`.
5. **Vercel**: no CI job for apps/web. Vercel's native Git integration
   (connect the repo, set root directory to `apps/web`) already does
   preview deploys per-PR and production deploys on merge better than a
   hand-rolled `vercel deploy` GitHub Actions step would — scripting a
   worse version of what the platform already does natively isn't worth
   it. Documented as exact dashboard steps in docs/NEEDS.md instead.
6. **k6 script** (`infra/k6/smoke-load-test.js`): §12's "rate limiting
   verified under load (simple k6 script)" — ramps concurrent virtual
   users against `POST /v1/query`, asserts the rate limiter returns 429s
   above the configured `rate_limit_per_min` rather than 500ing or
   hanging, and reports p50/p95 latency.
7. **`docs/runbook.md`** finalized per §11's minimum list: provider
   outage/fallback behavior, ingestion job stuck/failed, DB migration
   rollback, rotating API keys, re-indexing after an embedding model
   change — plus a deploy/rollback section given Phase 6 actually adds a
   deploy pipeline.
8. **`README.md`** finalized per §16's required sections. The eval
   results table cites real numbers only once a live run exists (§14
   Phase 4's deliverable, "baseline metrics committed to docs/" — never
   happened, since no Postgres/GROQ_API_KEY exists in this sandbox);
   marked as pending rather than filled with invented numbers.
9. **`docs/NEEDS.md`** finalized as the complete go-live checklist:
   Supabase (Postgres), Groq (already present), Fly.io, Vercel, Sentry,
   and every GitHub Actions secret `deploy.yml`/`evals.yml` read.

Not attempted this phase, disclosed rather than silently skipped: full
OpenTelemetry span instrumentation across the query/ingestion path (§11
asks for it generally; the task's explicit Phase 6 directive names
deploy.yml/fly.toml/k6/runbook/README specifically and doesn't mention
OTel, and it's a substantial standalone effort) — noted as an Open ADR
candidate below rather than built partially.

Cannot be verified live here: no Fly.io/Vercel/Sentry/Supabase accounts,
no GitHub Actions run, no real domain. Every config is built to be
structurally correct and internally consistent (validated where
possible — YAML syntax, `fly.toml` schema shape by inspection) and
marked "pending live verification."

### Completed

- **Real bug found and fixed: no rate limiting was ever enforced.**
  `api_keys.rate_limit_per_min` has existed as a schema column since
  Phase 0/1, but nothing checked it — every request succeeded regardless
  of volume. Found while writing the k6 script this phase explicitly
  asked for ("rate limiting verified under load"): there was nothing to
  verify. Added `middleware/rate_limit.py` (an in-memory, per-process
  fixed-window counter — simple and dependency-free, documented
  limitation: doesn't hold across multiple Fly machines/replicas, worth
  a formal ADR if that becomes real), a `RateLimitExceededError` (429,
  extending the existing `KanuniError` hierarchy), and wired it into
  `middleware/auth.py`'s `_authenticate` so every authenticated request
  is checked. 4 new unit tests
  (`apps/api/tests/middleware/test_rate_limit.py`). Also found and fixed
  a related test-isolation hazard while adding those tests: the new
  module-level `_windows` dict persists for the whole pytest session, and
  `tests/middleware/test_auth.py` reuses fixed (not random) API-key
  UUIDs across its tests — without a reset, accumulated request counts
  from unrelated tests could eventually trip the limiter for reasons
  having nothing to do with what a given test checks. Added an autouse
  `_reset_rate_limit_windows` fixture to `apps/api/tests/conftest.py`,
  mirroring the existing `_clean_kanuni_env` pattern in the same file.
- **Sentry wiring**, all three services, release-tagged from the
  deploying commit SHA:
  - `apps/api`, `apps/ingestion`: `sentry-sdk` +
    `telemetry/sentry.py`/`configure_sentry()` in each, called at
    startup with `Settings.sentry_dsn` / `Settings.release_sha` (both
    bare env vars, `SENTRY_DSN` / `RELEASE_SHA`, shared verbatim across
    services — a blank DSN is the SDK's own documented no-op, so no
    if-configured branching exists anywhere). Added explicit
    `capture_exception` calls at the two places an exception is caught
    and *not* re-raised (so Sentry's automatic ASGI-level capture would
    never see it): `error_handler.py`'s catch-all handler and
    `pipeline.py`'s per-document `_record_failure`.
  - `apps/web`: `@sentry/nextjs`, via Next.js's native
    `instrumentation.ts` (server) and `instrumentation-client.ts`
    (browser) hooks — no wizard, no webpack-plugin source-map upload
    (would need real `SENTRY_AUTH_TOKEN`/org/project to do anything
    useful; deliberately deferred rather than wired up against
    placeholder values). `NEXT_PUBLIC_SENTRY_DSN` is intentionally
    public — Sentry DSNs are submit-only, unlike `KANUNI_API_KEY`.
- **Docker/compose reconciliation**: `apps/api/Dockerfile` no longer
  bakes in `--reload` (now the production default Fly.io actually
  deploys; also now installs `dbmate` for `fly.toml`'s
  `release_command`) — `docker-compose.yml`'s `api` service adds
  `--reload` back via a `command:` override, so local dev is unaffected.
  Found and fixed a second real bug while doing this: `docker-compose.yml`'s
  `web` service set `NEXT_PUBLIC_API_URL`, a variable apps/web's code
  has never read since Phase 5's proxy-architecture decision — `make dev`
  would have brought up a frontend that could never reach the API.
  Replaced with `KANUNI_API_BASE_URL=http://api:8000` (Docker network
  service name) plus `env_file: .env` (for `KANUNI_API_KEY`, previously
  missing from this service entirely).
- **`fly.toml`** (production) **+ `fly.staging.toml`**: two Fly apps
  (`kanuni-api`, `kanuni-api-staging`), `release_command` running dbmate
  migrations pre-deploy (§12), `/readyz` HTTP health checks, a persistent
  volume per environment for `KANUNI_STORAGE_LOCAL_PATH` (see the Open
  ADR candidate on Supabase Storage below). Both TOML-syntax-validated.
- **`.github/workflows/deploy.yml`**: `flyctl deploy --remote-only`
  (Fly's own registry, no separate build/push step) → staging → a real
  smoke test (`infra/deploy/smoke_test.py`: `/readyz`, then one canned
  `/v1/query` call asserting `answered: true` and at least one citation)
  → `environment: production` (the manual approval gate — a GitHub
  Environment with required reviewers, exact setup in docs/NEEDS.md) →
  production deploy + its own smoke test → `getsentry/action-release`
  tagged with `github.sha`. apps/web is deliberately *not* deployed from
  here — see the Open ADR candidate below.
- **`infra/k6/rate-limit-load-test.js`**: targets `GET /v1/documents`
  (not `/v1/query` — exercises the same auth+rate-limit middleware
  without spending Groq credits or needing a populated corpus), asserts
  every response is a clean 200 or 429 (never 5xx) and that the limiter
  actually engages at least once under 10 concurrent VUs against a
  60/min default limit. Node-syntax-validated (`node --check`); not
  actually run (`k6` isn't installed in this sandbox).
- **`docs/runbook.md`** finalized: local stack (kept from Phase 0),
  deploying + rollback, provider outage/fallback behavior, ingestion job
  stuck/failed, DB migration rollback, rotating API keys, re-indexing
  after an embedding model change (§11's minimum list), rate limiting,
  and Sentry-based error triage — every command in it is real (matches
  the actual `fly.toml`/`deploy.yml`/schema), not aspirational.
- **`README.md`** finalized per §16's section list. The eval-results
  table is present with the correct column structure but every cell says
  `_pending_` rather than an invented number — `make eval` fills it in
  once run against a live backend. Demo GIF/live-demo-link is a similar
  explicit placeholder (needs a real deployment to record against).
- **`docs/NEEDS.md`** finalized: Supabase, Fly.io (including the exact
  `flyctl apps create` / `volumes create` / `secrets set` bootstrap
  commands), Vercel (dashboard steps, since no CI job does this — see
  Open ADR candidate below), Sentry, and a consolidated table of every
  GitHub Actions secret + the `production` environment's required-
  reviewers setup.
- `Settings.sentry_dsn`, `Settings.release_sha` added to both
  `apps/api/src/kanuni_api/config.py` and
  `apps/ingestion/src/kanuni_ingest/config.py`; `.env.example` updated
  with `RELEASE_SHA`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_RELEASE_SHA`,
  and a corrected `KANUNI_EVAL_JUDGE_LLM_MODEL` (Phase 4 had left a
  placeholder there — `KANUNI_EVAL_JUDGE_MODEL` — that didn't match the
  actual env var `Settings.eval_judge_llm_model` reads; found and fixed
  while reviewing `.env.example` end-to-end for this phase's NEEDS.md work).

### Verification

- `ruff check` / `ruff format --check`: clean (113 source files)
- `mypy --strict`: clean (113 source files)
- `pytest`: 138 passed, 9 skipped (unchanged skip set; +4 vs. Phase 5 —
  the new rate-limiter tests)
- `bun run --filter kanuni-web lint` / `typecheck` / `format:check`:
  clean; `bun run --filter @kanuni/shared typecheck`: clean
- `KANUNI_API_KEY=<dummy> bun run build` (production build): succeeds
  with the Sentry instrumentation hooks in place, same route table as
  Phase 5
- `.github/workflows/deploy.yml`, `.github/workflows/evals.yml`,
  `.github/workflows/ci.yml`, `docker-compose.yml`: YAML-syntax-validated
- `fly.toml`, `fly.staging.toml`: TOML-syntax-validated
- `infra/k6/rate-limit-load-test.js`: JS-syntax-validated (`node --check`)

Cannot be verified live: `flyctl deploy` actually succeeding (no Fly.io
account), the Vercel dashboard flow, Sentry actually receiving an event,
the k6 script's actual load behavior, and `deploy.yml`'s full run
end-to-end (no GitHub Actions execution, no repository secrets
configured) — all "built, pending live verification."

### Open ADR candidates

- **The ingestion worker has no Fly.io deployment.** `deploy.yml` and
  `fly.toml` cover `apps/api` only — the worker (`python -m
  kanuni_ingest`, `apps/ingestion/Dockerfile`) currently only runs via
  `docker compose` locally. It needs the same treatment (a
  `fly.ingestion.toml`, likely as a Fly "worker" process with no public
  `http_service`, plus a `deploy.yml` job) before real, non-fixture
  documents can be ingested against a deployed environment. Scoped out
  of this phase for time, not forgotten — flagged here and in
  `docs/NEEDS.md`/`docs/runbook.md` rather than silently absent.
- **In-memory rate limiting doesn't hold across multiple Fly
  machines/replicas** — each machine enforces its own independent
  60/min window, so N machines effectively allow N×60/min. Fine today
  (`min_machines_running = 1` in both `fly.toml` configs), but would
  need a shared store (Redis, or a Postgres-backed counter) the moment
  horizontal scaling is turned on. Documented in `rate_limit.py`'s
  module docstring and `docs/runbook.md`.
- **Document storage uses a Fly volume, not Supabase Storage.** Phase
  1 already flagged this as deferred (see `.env.example`'s unread
  `KANUNI_STORAGE_BUCKET_URL` etc.); Phase 6 just makes the deferral
  concrete by actually provisioning the Fly-volume alternative for a
  real deployment rather than leaving it purely local. Swapping in
  Supabase Storage later only requires a new `DocumentStorage`
  implementation (§4.4's whole point), not an architecture change.
- **No OpenTelemetry span instrumentation.** §11 asks for it generally
  ("OpenTelemetry spans for the full query path"); the task's Phase 6
  directive named specific deliverables (deploy.yml, fly.toml, k6,
  runbook, README) that didn't include it, and it's a substantial
  standalone effort (span instrumentation through embed → dense → sparse
  → fuse → rerank → generate → validate, plus ingestion stages) better
  scoped as its own piece of work than squeezed in at the end of this one.
  `KANUNI_OTEL_EXPORTER_OTLP_ENDPOINT` already exists in `.env.example`
  as a placeholder for when this happens.
- **Rate-limit 429 responses don't set a `Retry-After` header.** Cheap
  to add, deliberately left out to keep the error hierarchy change
  minimal — worth doing if client implementations start polling
  aggressively after a 429 instead of backing off.

### Commit message

```
phase-6: ship & harden (Sentry, rate limiting, Fly.io, k6, docs)

- Fixed a real bug: rate limiting was never enforced despite
  api_keys.rate_limit_per_min existing since Phase 0/1 — added an
  in-memory per-key fixed-window limiter (middleware/rate_limit.py),
  wired into middleware/auth.py, 4 new tests, plus a test-isolation fix
  (autouse window-reset fixture in conftest.py)
- Sentry wiring in apps/api, apps/ingestion (sentry-sdk,
  telemetry/sentry.py, explicit capture at the two catch-and-don't-
  re-raise sites) and apps/web (@sentry/nextjs via instrumentation.ts /
  instrumentation-client.ts) — release-tagged from the deploying commit
  SHA everywhere
- Fixed a second real bug: docker-compose.yml's web service set a
  NEXT_PUBLIC_API_URL apps/web's code has never read since Phase 5 —
  `make dev` would have shipped a frontend that couldn't reach the API;
  replaced with KANUNI_API_BASE_URL pointed at the api service
- apps/api/Dockerfile is now the production image Fly.io actually
  deploys (--reload moved to a docker-compose.yml command: override;
  dbmate added for fly.toml's release_command)
- fly.toml + fly.staging.toml (apps/api, staging + prod Fly apps,
  migrations-on-deploy, /readyz health checks, persistent volumes)
- .github/workflows/deploy.yml: staging deploy -> real smoke test
  (infra/deploy/smoke_test.py) -> manual approval gate -> prod deploy +
  smoke test -> Sentry release tagging
- infra/k6/rate-limit-load-test.js: verifies the rate limiter under load
- docs/runbook.md, README.md finalized (real commands throughout; eval
  results table and demo GIF/link left as explicit "pending" rather than
  invented numbers/links)
- docs/NEEDS.md finalized: Supabase, Fly.io, Vercel, Sentry, and every
  GitHub Actions secret + the production environment's approval-gate setup
- Fixed a stale .env.example entry (KANUNI_EVAL_JUDGE_MODEL ->
  KANUNI_EVAL_JUDGE_LLM_MODEL, matching what Settings actually reads)

Tests: 138 passed, 9 skipped (+4 vs. Phase 5 — rate-limiter tests).
ruff, mypy --strict, frontend lint/typecheck/format: all clean.
Production build (apps/web) succeeds.

Built, pending live verification: everything that needs a Fly.io/
Vercel/Sentry/Supabase account or a GitHub Actions run to actually
execute — none exist in this sandbox (see docs/NEEDS.md).
```

---

## Post-handoff: live Supabase connection, RLS, Supabase Storage

Not a numbered phase — done after Phase 6's handoff, once the maintainer
connected a real Supabase project (first via MCP, then by supplying the
pooled connection string directly in `.env`). Recorded here because it's
real, verified work against live infrastructure, not just more "built,
pending live verification."

- **Live database.** Installed `dbmate` locally (user-local bin, no root
  on this box), applied `infra/migrations/0001` and `0002` against the
  real Supabase Postgres, and verified with the app's actual
  `create_pool`/asyncpg code (not just `psql`): all 6 tables, the HNSW
  index, the FTS GIN index, and pgvector 0.8.2 all present and correct.
  Found and fixed a bug in `.env` in the process: `KANUNI_DATABASE_URL`
  (what the app reads) was still `localhost` even after `DATABASE_URL`
  (what dbmate reads) had been pointed at Supabase — the app would have
  silently kept failing to connect.
- **Row Level Security** (migration `0003`): every app table had RLS
  disabled, which Supabase's security advisor flags. Enabled RLS with
  zero policies on all 6 — verified the connecting role (`postgres`)
  owns every table, so Postgres's owner-bypass-RLS default means the app
  is completely unaffected while every other role (anon/authenticated —
  i.e. PostgREST/browser-side Supabase clients, if ever exposed) gets
  default-deny. Confirmed both `relrowsecurity = true` on all 6 tables
  and a real `SELECT` through the app's pool still succeeding.
- **Storage: Supabase Storage replaces local-filesystem storage +
  the Fly volume entirely**, and `GET /v1/documents/{id}/file` (added in
  Phase 5) is removed — the frontend links straight to the document's
  Supabase Storage public URL instead of proxying bytes through the API.
  Decided via `AskUserQuestion` (scope options: storage-only vs.
  storage+auth vs. "something else") — maintainer picked storage-only,
  smallest/lowest-risk cut, auth model (`api_keys`, §4.3) untouched.
  - `SupabaseStorage` (plain `httpx` calls to Supabase's Storage REST
    API, no SDK dependency — matches `GroqLLMProvider`'s existing
    pattern) added to both `apps/api/src/kanuni_api/storage.py` and
    `apps/ingestion/src/kanuni_ingest/storage.py` (own copies, ADR
    0005). The bucket is public (the corpus is public regulatory text),
    so only writes need the service-role key; reads use the public URL.
  - `apps/api`'s storage moved from being constructed inline per-route
    to a proper FastAPI dependency (`StorageDep`/`get_storage`, mirroring
    `EmbeddingProviderDep`/`RerankerProviderDep`/`LlmProviderDep`) —
    needed so tests can override it instead of hitting real Supabase
    Storage over the network (§13). `LocalFilesystemStorage` is kept in
    `apps/ingestion` deliberately, test-only now — the real-pipeline
    integration tests need a fast, dependency-free storage backend, and
    it already is exactly that.
  - Added `ResolvedCitation.source_url: str | None`, computed in
    `query_service.py` from `documents_repository.find_storage_path` +
    a new pure `storage.public_url()` helper — no `DocumentStorage`
    instance needed for that, since building the URL is just string
    formatting.
  - `fly.toml`/`fly.staging.toml`: dropped the `[[mounts]]` volume
    blocks entirely — nothing left to persist on the Fly machine.
    `docker-compose.yml`: dropped the `document-storage` volume and
    `KANUNI_STORAGE_LOCAL_PATH` env vars from `api`/`ingestion` (their
    `KANUNI_DATABASE_URL` override to the local `db` service is
    deliberately kept — that's a separate, out-of-scope decision from
    what was asked here, so `make dev` still gets its own local Postgres
    by default even though `.env` now also has a real Supabase URL).
  - Bucket (`documents`, public, 100MB limit, `application/pdf` only)
    created via a direct SQL insert into `storage.buckets` (the same
    live connection already in hand) rather than the Storage API.
  - `docs/NEEDS.md`, `.env.example`, `README.md` updated; the two
    obsolete `GET /v1/documents/{id}/file` tests removed, `test_admin.py`
    and the admin-upload integration test switched from a `tmp_path`-
    backed real `LocalFilesystemStorage` to the dependency-override
    pattern with a new shared `FakeDocumentStorage` (`api_fakes.py`).

### Open ADR candidate (new)

- `storage.write()` failures (`httpx.HTTPStatusError`) aren't mapped to
  a domain exception — they fall through to the generic `internal_error`
  500 handler. Fine today (an upload failure is rare and the generic
  message is still safe/non-leaky), but a dedicated `StorageError` would
  give callers a clearer, more specific signal if this turns out to
  matter in practice.

---

## Post-handoff, round 2: schema_migrations RLS, Hugging Face Spaces,
## GlitchTip, Supabase client scaffolding, live end-to-end verification

Continuing the post-handoff work above, in the same session.

- **`schema_migrations` RLS** (migration `0004`): round 1's RLS migration
  deliberately excluded `schema_migrations` (dbmate's own bookkeeping
  table, not "app data") — maintainer feedback: it's still in the public
  schema and Supabase's advisor flags it identically, so there was no
  real reason to leave it out. Split into its own migration rather than
  amending `0003` (already applied live; migrations are not edited after
  the fact). Applied and verified: all 7 public tables now have RLS
  enabled, `SELECT count(*) FROM documents` through the app's pool still
  succeeds (owner bypass, same reasoning as `0003`).
- **Fly.io → Hugging Face Spaces** (maintainer preference: HF's free CPU
  Docker tier has no time-boxed trial, unlike Fly's). Removed
  `fly.toml`/`fly.staging.toml`. Added a root-level `Dockerfile`
  (content mirrors `apps/api/Dockerfile` — Hugging Face Spaces' Docker
  SDK requires the file at repo root by exact name; the two must be kept
  in sync by hand, Docker has no include directive) and
  `infra/deploy/deploy_to_hf_space.sh`, which builds a minimal deploy
  bundle (Dockerfile + the source the image needs + a generated
  Space-specific `README.md` frontmatter) and force-pushes it as a
  single commit to the Space's git remote — deliberately not this repo's
  full history, and deliberately not reusing our real `README.md` (which
  would fight Hugging Face's own frontmatter convention for that exact
  file). `apps/api/Dockerfile` no longer installs `dbmate`: Hugging Face
  Spaces has no Fly-style pre-deploy release-command hook, so
  `deploy.yml` gained a dedicated `migrate` job that runs `dbmate up`
  directly from the GitHub Actions runner against `DATABASE_URL` before
  either deploy job runs — arguably cleaner than embedding dbmate in the
  image at all. `RELEASE_SHA` propagation is a known, disclosed gap:
  unlike Fly's `--env` flag, there's no scripted way to set a Space
  secret per-deploy in what's built here, so it stays `"dev"` on every
  Hugging Face deploy until that's extended to call Hugging Face's API
  (see Open ADR candidates below) — documented rather than silently
  claimed to work.
- **Sentry → GlitchTip** as the documented default: zero code changes
  (`sentry-sdk`/`@sentry/nextjs` are protocol-generic, GlitchTip
  implements the same event-ingest API), purely a `docs/NEEDS.md`
  sign-up-steps swap, with real Sentry noted as a same-env-var drop-in
  for anyone who already has an account. `deploy.yml`'s old
  `sentry-release` job (tagging a release via `getsentry/action-release`)
  was removed rather than pointed at GlitchTip — that action calls
  Sentry's release-management API, which GlitchTip isn't confirmed to
  implement, and a step that might silently no-op or fail isn't better
  than no step; the part that actually matters for triage (every event
  carrying a `release` tag) already happens via SDK init at runtime.
- **Supabase client SDK scaffolding in apps/web**
  (`@supabase/supabase-js`, `@supabase/ssr` — installed with `bun add`,
  not `npm install`, per this project's standing package-manager
  decision). The maintainer's instructions included running
  `npx shadcn@latest add @supabase/supabase-client-nextjs` to scaffold
  the client files; tried it (via `bunx` and `npx`, since apps/web has
  no shadcn/ui setup at all) and it dropped into an interactive
  multi-step wizard (component library choice, a "Nova/Vega/Maia/..."
  design-preset picker) with no non-interactive flag that skips it —
  that wizard installs a whole shadcn/ui design system (Base or Radix
  primitives, a preset color/font system), which doesn't fit a codebase
  that has been hand-styled with Tailwind utility classes throughout, so
  running it to get 2-3 boilerplate files would have imported real
  unwanted design-system weight for no functional benefit. Hand-wrote
  `apps/web/src/lib/supabase/{client,server}.ts` instead, matching
  Supabase's own documented `@supabase/ssr` App Router pattern exactly
  (browser client via `createBrowserClient`, server client via
  `createServerClient` + `next/headers`'s `cookies()`) — same end state
  for the actual ask (working Supabase client utilities ready to import)
  without the design-system side effect. Not wired to any feature yet,
  by design — no auth/realtime/storage feature exists in the UI to need
  them, so no `middleware.ts` session-refresh helper was added either
  (nothing to refresh a session for yet); both files exist purely as
  ready-to-use scaffolding for whenever one is built.
  - `apps/web/.env.local` created (gitignored) with real values,
    including `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
    from the maintainer's instructions, plus `KANUNI_API_BASE_URL` and a
    **new real `KANUNI_API_KEY`** (`query`-scoped, bootstrapped directly
    against the live database — `api_keys.name = 'local dev (apps/web)'`)
    — this also closed a real gap noticed while doing this: apps/web had
    no local `.env.local` at all before now, so `bun run dev` outside
    Docker had never actually had `KANUNI_API_KEY` available; only the
    Docker Compose path (`env_file: .env`) did.
- **Live end-to-end verification** (new capability this round — the live
  Supabase connection plus a real API key made this possible for the
  first time this project): started the real `apps/api` (uvicorn) and
  `apps/web` (`next dev`) processes locally, both against the live
  Supabase database and real `.env`/`.env.local` values, and confirmed
  with real HTTP requests: `/healthz`/`/readyz` both `200`,
  `GET /v1/documents` (real auth, real rate limiter, real RLS-enabled
  query) returns `[]` correctly (no data ingested yet), all three
  frontend pages (`/`, `/documents`, `/about`) return `200`, the
  `/api/documents` proxy round-trips through the real backend to the
  real database, and the About page's live document count renders "0
  documents currently indexed" from genuinely live data rather than its
  designed fallback text. This is meaningfully stronger evidence than
  anything achievable earlier in this project (no live infrastructure
  existed until this session) — still not tested: the actual
  question-answering path (`POST /v1/query`), which needs a populated
  corpus and would trigger multi-GB embedding/reranker model downloads;
  deliberately not run here given the time/bandwidth cost, left for the
  maintainer.

### Open ADR candidates (new)

- **`RELEASE_SHA` isn't propagated to Hugging Face Spaces per-deploy.**
  `deploy_to_hf_space.sh` only pushes code; setting a Space secret from
  CI would need either the `huggingface_hub` Python API or direct calls
  against Hugging Face's REST API for repository secrets/variables —
  skipped rather than guessed at without a live account to verify the
  exact request shape against. Every event currently reports
  `release: "dev"` from any Hugging Face-deployed environment until this
  is built.
- **Staging and production share one Supabase database and one
  Hugging Face deploy target's worth of Groq/GlitchTip credentials**
  (`docs/NEEDS.md`'s Hugging Face Spaces section notes this as an
  accepted-for-now simplification). A staging migration or bad data
  write currently has a real blast radius into what's nominally
  "production" data — acceptable for a small project today, worth
  revisiting (a second Supabase project) before real users depend on it.

---

## Post-handoff, round 3: GlitchTip wiring finished + a real §13 violation
## found and fixed

- Added GlitchTip's own recommended `auto_session_tracking=False` /
  `traces_sample_rate=0.01` to both Python `configure_sentry()` calls.
  Tried the same on the two `@sentry/nextjs` `Sentry.init()` call sites;
  `tsc` immediately rejected `autoSessionTracking` — not a valid option
  in the installed SDK version's types (apparently dropped/renamed in a
  more recent Sentry JS SDK release than GlitchTip's docs assume). Kept
  `tracesSampleRate` (which the types do accept) and documented the
  discrepancy inline rather than silently dropping the option with no
  explanation.
- Live-verified the real GlitchTip DSN with `sentry_sdk.capture_message()`
  + `flush()` from a standalone script — got back a real `event_id` with
  no transport error, confirming the DSN and project are correctly wired
  before spending any more time on it.
- **Found a real, serious §13 violation while re-running the test suite
  after wiring the DSN into `.env`**: pytest logged "Sentry is attempting
  to send 2 pending events" — meaning `apps/api/tests/test_main.py`
  (which calls `create_app()` directly, unmocked) had been constructing
  the *real* `sentry_sdk` client with the *real* DSN, and the
  `traces_sample_rate` just added was enough to probabilistically sample
  and actually transmit real trace events during a normal test run. Root
  cause was two layered bugs in `conftest.py`'s `_clean_kanuni_env`
  fixture, both fixed:
  1. It only stripped `KANUNI_`-prefixed env vars from `os.environ` —
     `SENTRY_DSN`, `GROQ_API_KEY`, `SUPABASE_URL`, and
     `SUPABASE_SERVICE_ROLE_KEY` are bare by deliberate design (matching
     each provider's own conventional variable name — see Phase 3's
     notes on `GROQ_API_KEY`), so a maintainer's real values for those
     were never touched. Fixed by reading `Settings.model_fields` for
     every field's `validation_alias` instead of hardcoding a list, so a
     future bare-var field can't reintroduce the same gap silently.
  2. More fundamentally: even stripping *every* var from `os.environ`
     wouldn't have been enough. `pydantic-settings`' `env_file=".env"`
     is a *second*, separate source it reads directly off disk on every
     `Settings()` construction — a var merely deleted from the process
     environment still resolves to whatever the real `.env` *file*
     contains. `monkeypatch.delenv` cannot prevent this. Fixed by also
     `monkeypatch.setitem(Settings.model_config, "env_file",
     "/nonexistent/.env")`, which cleanly disables dotenv loading for
     the duration of each test — the actual fix; (1) alone would not
     have been sufficient and the leak would have continued.
  - This means **`KANUNI_DATABASE_URL` — the real Supabase connection
    string — had also been silently reachable via `Settings()` in every
    test this entire session**, not just `SENTRY_DSN`. No test happened
    to exercise an unmocked code path that would have opened that
    connection for real (every DB-touching test mocks at the repository/
    connection-injection layer, never lets `Settings().database_url`
    reach an actual `asyncpg.connect` call) — but that was luck of what
    existing tests happen to do, not a structural guarantee, until this
    fix.
  - Added `test_defaults_are_used_even_when_a_real_env_file_exists_on_disk`
    to `test_config.py` as a standing regression guard, asserting every
    bare-var field resolves to its safe class default despite the real
    `.env` file being present on disk in this environment.
  - Verified: re-ran the full suite after the fix — no more "pending
    events" message, 137 passed (+1, the new regression test), 9 skipped
    (unchanged skip set).

## Post-handoff, round 4 — live Ask/Documents hang, two real bugs found

The maintainer ran `apps/web` + `apps/api` live against the real Supabase
instance and reported (via screenshot) that both the Documents page and
the Ask page hung indefinitely in their loading-skeleton state, with no
error surfaced anywhere in the browser. Diagnosed both root causes by
reading the live API server's structured (`structlog`) log output rather
than guessing — two independent, real bugs, both now fixed and verified.

- **Bug 1 — blocking synchronous model calls froze the entire event
  loop.** `apps/api/src/kanuni_api/embedding.py`
  (`Bgem3EmbeddingProvider.embed_query`) and `reranker.py`
  (`Bgereranker.score`) were declared `async def` but called
  `sentence-transformers` directly in the coroutine body — synchronous
  code that, on first call, also downloads the model (`BAAI/bge-m3`,
  multiple GB) from Hugging Face. `uvicorn` here runs a single process/
  single event loop; blocking it froze *every* concurrent request,
  including the completely unrelated `GET /v1/documents` the Documents
  page was stuck on. Independently corroborated: the stuck server
  process didn't respond to `SIGTERM` at all (only `SIGKILL` worked) —
  consistent with the event loop never getting a chance to process the
  signal. Fixed in all three call sites (`apps/api/embedding.py`,
  `apps/api/reranker.py`, and the `apps/ingestion` copy of
  `embedding.py`, fixed for consistency even though that worker only
  processes one document at a time today) by moving the actual
  synchronous work into a private `_encode`/`_predict` method and
  calling it via `await asyncio.to_thread(...)` from the public
  `async def` method, each with a comment explaining why.
- **Bug 2 — concurrent use of one asyncpg connection.**
  After fixing bug 1 and re-testing, the API log showed a second, real
  error on the very next query: `asyncpg.exceptions._base.InterfaceError:
  cannot perform operation: another operation is in progress`.
  `apps/api/src/kanuni_api/services/retrieval_service.py`'s `retrieve()`
  ran `dense.dense_search()` and `sparse.sparse_search()` concurrently
  via `asyncio.gather()` — both sharing the *same* `asyncpg.Connection`,
  which can only execute one operation at a time. This had shipped since
  Phase 2 without ever being caught, because no prior test or eval
  exercised `retrieve()` against a real database with this exact
  connection-sharing pattern (all `retrieve()`-level tests mock
  `dense_search`/`sparse_search` directly). Fixed by running the two
  searches sequentially instead of via `asyncio.gather`, with an inline
  comment noting that real parallelization (acquiring a second
  connection from the pool for one of the two calls) is deferred — see
  Open ADR candidates below.
- Verified both fixes: `ruff check`, `ruff format --check`, and
  `mypy --strict` clean on every changed file; full suite
  `137 passed, 9 skipped` (unchanged counts — no test exercises either
  of the real code paths that were broken, by design, per §13). Restarted
  the live API server and re-tested for real: `GET /v1/documents` now
  responds in under a second (was: infinite hang), and a real
  `POST /v1/query` request completes end-to-end with a `done` SSE event
  (39.4s latency — genuinely slow on this sandbox's CPU-only inference,
  not a hang) and no `InterfaceError` in the log. The query itself
  returned `"confidence":"refuse"`, expected since no documents are
  ingested into this Supabase instance yet — the point of this round was
  confirming the pipeline completes at all, not the answer's quality.

### Open ADR candidates (new this round)

- `retrieval_service.retrieve()`'s dense/sparse search now runs
  sequentially on one connection rather than truly in parallel — correct
  but leaves latency on the table. Proper fix is acquiring a second
  connection from the pool for one of the two calls; deferred since it
  touches the connection-lifecycle contract between `dependencies.py`
  and the retrieval layer, worth a deliberate decision rather than a
  quick patch under live-debugging pressure.
- Both blocking-call and connection-sharing bugs escaped every existing
  test and eval because nothing exercises `retrieve()` end-to-end
  against a real Postgres with real (non-fake) embedding/reranker
  providers — the fixture/fake-based unit tests are correct in
  isolation but can't catch this class of bug by construction. Worth
  considering a narrowly-scoped integration test (real Postgres, fake
  embedding/reranker to avoid the model-download cost, but a *real*
  shared connection) specifically to guard against connection-sharing
  regressions, since the current test suite structurally cannot.
