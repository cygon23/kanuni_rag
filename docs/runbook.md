# Runbook

Operational procedures for Kanuni. Written from the actual deploy
pipeline (`.github/workflows/deploy.yml`, `Dockerfile`,
`infra/deploy/deploy_to_hf_space.sh`) and codebase behavior — every
command here is real and matches what's checked into the repo, not
aspirational. Commands that touch a live environment (Hugging Face,
Supabase, GlitchTip) require the setup in [docs/NEEDS.md](NEEDS.md) to
already be done.

## Local stack

- Bring the stack up: `make dev` (`docker compose up --build`)
- Liveness: `curl http://localhost:8000/healthz`
- Readiness (checks the database): `curl http://localhost:8000/readyz`
- Tear down: `make down`

## Deploying

`deploy.yml` runs automatically on every push to `main` that touches
`apps/api/**`, the migrations, or the deploy configs: run migrations →
deploy staging (Hugging Face Space) → smoke test → **manual approval
gate** → deploy production. To deploy manually (e.g. to re-run a failed
step):

```bash
HF_USERNAME=<your HF username> HF_TOKEN=<your HF token> \
  infra/deploy/deploy_to_hf_space.sh kanuni-api-staging "Kanuni API (staging)"
HF_USERNAME=<your HF username> HF_TOKEN=<your HF token> \
  infra/deploy/deploy_to_hf_space.sh kanuni-api "Kanuni API"
```

The manual approval gate is a GitHub Environment named `production` with
required reviewers (Settings → Environments → production) — the
`deploy-production` job in `deploy.yml` pauses until an approver clicks
Approve in the Actions run. If a deploy needs to happen faster than that
allows (an active incident), an approver can still approve immediately;
there's no way to bypass the gate from the CLI, by design.

apps/web deploys via Vercel's own Git integration, not this pipeline —
merges to `main` deploy automatically once the project is connected (see
docs/NEEDS.md).

### Rollback

Each deploy force-pushes a fresh single-commit bundle to the Space (see
`deploy_to_hf_space.sh`'s header comment) — the Space's own git history
isn't the source of truth, this repo is. To roll back:

```bash
git checkout <last-good-commit>
HF_USERNAME=<your HF username> HF_TOKEN=<your HF token> \
  infra/deploy/deploy_to_hf_space.sh kanuni-api "Kanuni API"
git checkout main   # don't stay on a detached HEAD
```

If the bad release included a migration, see "DB migration rollback"
below **before** rolling the app back — rolling back code against a
schema the old code doesn't expect will just move the failure elsewhere.

## Provider outage / fallback behavior

- **Groq (generation) down or rate-limited:** `GroqLLMProvider` raises
  `ProviderTimeoutError` / `ProviderRateLimitError`
  (`apps/api/src/kanuni_api/generation/llm_client.py`).
  `FallbackLLMProvider` catches both and retries against a fallback
  provider *if one is configured* (`KANUNI_LLM_FALLBACK_PROVIDER`) — as
  of this phase, no second provider implementation exists, so an outage
  currently surfaces as a `provider_timeout` / `provider_rate_limit`
  error response (mapped to 504 / 429) rather than a silent fallback.
  Known limitation documented in `FallbackLLMProvider`'s docstring: a
  fallback that fires *after* some text has already streamed to the
  client would mix partial output — acceptable today only because Groq
  reports these failures before the first token in the overwhelming
  majority of cases.
- **Groq (ingestion metadata extraction) down:** `versioning.py` resolves
  `reference_number` and amendment/supersession relations via regex on
  the source text regardless — only `issuing_body` and `effective_date`
  go unset until the next successful run. Not a stuck pipeline, just
  incomplete metadata; re-run ingestion for that document once Groq
  recovers.
- **Supabase Storage down:** document upload
  (`POST /v1/admin/documents`) fails with an unhandled 500
  (`SupabaseStorage.write()`'s `httpx.HTTPStatusError` isn't specifically
  caught — see `docs/PROGRESS.md`'s post-Phase-6 Open ADR candidate on
  adding a dedicated `StorageError`); existing citations still resolve,
  just without a working "open source PDF" link
  (`ResolvedCitation.source_url`).
- **Embedding/reranker model unavailable** (OOM, not yet downloaded,
  etc.): both `Bgem3EmbeddingProvider` and `Bgereranker` load lazily on
  first use — a cold-start failure here fails the first request after a
  deploy/restart, not startup itself. Check `/readyz` and the Space's
  memory usage in its dashboard; Hugging Face's free CPU Docker tier's
  RAM is a starting point, not a verified minimum for bge-m3 +
  bge-reranker-v2-m3 running together — upgrade the Space's hardware tier
  if OOM kills appear in its logs.

## Ingestion job stuck or failed

- Check status: `GET /v1/documents/{id}` for `pipeline_status`, or query
  `ingestion_jobs` directly for the per-stage attempt history and
  `error_details`.
- A failed document sits at `pipeline_status = 'failed'`
  (`kanuni_ingest/pipeline.py`'s `_record_failure`) — it does **not**
  block other documents; the worker loop moves on. As of this phase,
  failures are also reported to GlitchTip/Sentry
  (`sentry_sdk.capture_exception` in `_record_failure`) — check there
  first for the actual traceback.
- Resumability: `PipelineRunner.run` resumes from the last *completed*
  stage (`fetched → extracted → chunked → embedded → indexed`), so
  re-running ingestion for a `failed` document (re-upload via `kanuni
  ingest`, matching SHA-256, is a no-op — instead re-trigger processing
  directly, e.g. by restarting the worker or, for a one-off, invoking
  `PipelineRunner.run` for that document id) does not duplicate chunks or
  redo completed stages.
- If a document is stuck (no stage progress, no `failed` status, no
  error) rather than actually failed: the worker only picks up documents
  once per `KANUNI_WORKER_POLL_INTERVAL_SECONDS` (default 5s) — check the
  worker process is actually running (today the worker only runs via
  `docker compose` locally; it has no deployment of its own yet — see the
  Open ADR candidate in `docs/PROGRESS.md`'s Phase 6 notes) before
  assuming a code bug.

## DB migration rollback

Every migration in `infra/migrations/` has a tested down path (verified
in `ci.yml`'s `integration-tests` job, which runs the full up/down cycle
against a real Postgres on every push touching migrations).

```bash
# Roll back the most recent migration:
dbmate --migrations-dir infra/migrations down

# Against a specific environment, set DATABASE_URL first:
DATABASE_URL=<Supabase connection string> dbmate --migrations-dir infra/migrations down
```

`deploy.yml`'s `migrate` job runs `dbmate ... up` automatically before
every deploy — if a migration itself is the problem, `dbmate ... down`
against `DATABASE_URL`, then deploy the previous app release (see
Rollback above) rather than a new one that expects the migration.

## Rotating API keys

There is no key-issuing endpoint yet (see `docs/PROGRESS.md`'s Phase 5
"Open ADR candidates" for why, and `docs/NEEDS.md` for how to bootstrap
the first key) — rotation today is also a direct database operation:

```sql
-- 1. Issue the replacement (generate a key + hash as in docs/NEEDS.md):
INSERT INTO api_keys (key_hash, name, scopes, rate_limit_per_min)
VALUES ('<new key''s sha256 hex digest>', 'descriptive name', '{query}', 60);

-- 2. Roll callers over to the new key.

-- 3. Revoke the old one (never DELETE — keeps queries/audit history intact):
UPDATE api_keys SET revoked_at = now() WHERE key_hash = '<old key''s sha256 hex digest>';
```

`api_keys_repository.find_active_by_key_hash` only matches rows where
`revoked_at IS NULL`, so a revoked key stops authenticating immediately
on its very next request — no propagation delay to account for.

## Re-indexing after an embedding model change

Changing `KANUNI_EMBEDDING_MODEL` (or `KANUNI_RERANKER_MODEL`) does
**not** retroactively re-embed existing chunks — old chunks keep
whatever vector their original model produced, and dense search would
silently compare query embeddings from the new model against document
embeddings from the old one (garbage similarity scores, not an error).

1. Deploy the config change (new model name).
2. Re-run ingestion for every already-ingested document so `chunks.embedding`
   is regenerated under the new model. There is no bulk "re-embed in
   place" command yet — re-ingesting re-runs the full pipeline
   (idempotent on `file_sha256`, but will redo the embed/index stages
   since the resumability check is per-stage-completion, not
   per-model-version — a real gap if this needs to happen often; worth a
   `chunks.embedding_model` column and a dedicated re-embed command if
   model changes turn out to be frequent).
3. Until step 2 finishes for a given document, expect degraded (not
   broken) retrieval quality for it — a single dense-search query mixing
   old- and new-model chunk vectors will rank inconsistently, but nothing
   errors.

## Rate limiting

Enforced per API key (`apps/api/src/kanuni_api/middleware/rate_limit.py`)
against `api_keys.rate_limit_per_min` (default 60), checked on every
authenticated request. It's an in-memory, per-process fixed-window
counter — correct for a single machine, **not** correct across multiple
replicas of the same Space (each would enforce its own independent
limit, effectively multiplying the real ceiling by the replica count).
Verified under load with `infra/k6/rate-limit-load-test.js`:

```bash
k6 run -e BASE_URL=https://<your-hf-username>-kanuni-api-staging.hf.space \
       -e API_KEY=<a query-scoped key> \
       infra/k6/rate-limit-load-test.js
```

Passing means: every response was a clean 200 or 429 (never a 5xx or
timeout) and the limiter actually engaged at least once. Hugging Face
Docker Spaces run as a single container by default — if that ever
changes, revisit this: a shared store (Redis, or a Postgres-backed
counter) would be needed for the limit to hold globally.

## Error triage (GlitchTip)

Errors from `apps/api`, `apps/ingestion`, and `apps/web` all report to
the same GlitchTip project (`SENTRY_DSN`, `Settings.sentry_dsn` /
`NEXT_PUBLIC_SENTRY_DSN` — still named for the Sentry-compatible protocol
they speak, not the specific vendor; see docs/NEEDS.md), tagged with
`environment` (`development` / `staging` / `production`) and `release`
(the deploying commit SHA — set by `deploy.yml`'s
`--env RELEASE_SHA=$GITHUB_SHA` equivalent via the Space's secrets, or
Vercel's own `VERCEL_GIT_COMMIT_SHA` for the frontend). Filter by
environment first to separate staging noise from production incidents;
the release tag links an error straight back to the exact commit that
shipped it. A real Sentry account is a drop-in alternative — same env
vars, same SDKs, just a different DSN.
