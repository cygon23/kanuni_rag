# NEEDS — what the maintainer must provide or set up

Per CLAUDE.md's Autonomous Execution Protocol: every external credential,
account, or resource the autonomous phases 2–6 depend on is listed here,
never invented or faked. Each item names the exact env var it fills and the
setup steps to get it. Nothing below blocks the code from being built and
tested (all tests use mocked providers) — it blocks *live* verification and
deployment only.

## Groq API key — generation (Phase 3)

- **Env var:** `GROQ_API_KEY`
- **Fills:** `GroqLLMProvider`'s auth header in
  `apps/api/src/kanuni_api/generation/llm_client.py`; read via
  `Settings.groq_api_key` (`.env.example`'s `GROQ_API_KEY`). Also used, as
  a *different* model (`Settings.eval_judge_llm_model`), as the answer-eval
  judge in `evals/run_answer_eval.py` (Phase 4).
- **Setup:**
  1. Sign up / log in at https://console.groq.com
  2. Create an API key under "API Keys"
  3. Set `GROQ_API_KEY=<key>` in your `.env` (never commit it)
  4. For CI: add the same value as a GitHub Actions repository secret
     named `GROQ_API_KEY` (Settings → Secrets and variables → Actions) —
     `.github/workflows/evals.yml`'s answer-eval job reads it from there,
     and skips itself (not fails) if it isn't set, e.g. on fork PRs.
- **Blocks:** live generation via `POST /v1/query`; the eval harness's
  answer-quality metrics (§10, Phase 4) both locally and in
  `evals.yml`'s CI job; nothing else — all tests mock `LLMProvider`.

## Groq API key — ingestion metadata extraction (Phase 1)

- **Env var:** `KANUNI_GROQ_API_KEY`
- **Fills:** `GroqMetadataExtractionProvider`'s auth header in
  `apps/ingestion/src/kanuni_ingest/metadata_extraction.py`, used by the
  ingestion worker (`apps/ingestion/src/kanuni_ingest/__main__.py`) to
  supplement regex-based metadata extraction (issuing body, effective
  date) during ingestion pipeline stage 4 (§7). Deliberately a distinct
  env var from `GROQ_API_KEY` above, even though both may point at the
  same Groq account/key — the two services (api, ingestion) don't share
  configuration.
- **Setup:** same Groq account as above; either reuse the same key value
  or create a second one, and set `KANUNI_GROQ_API_KEY=<key>` in your
  `.env` (never commit it).
- **Blocks:** the ingestion worker processing real (non-test) documents
  past pipeline stage 4 — `reference_number` and amendment/supersession
  relations still resolve via regex without this key (see
  `versioning.py`'s module docstring), but `issuing_body` and
  `effective_date` will stay unset. Not required for
  `evals/prepare_eval_corpus.py` (Phase 4), which uses a no-op stand-in
  deliberately — see that script's module docstring.

## Kanuni admin API key for the ingestion CLI (Phase 1)

- **Env var:** `KANUNI_ADMIN_API_KEY` (plus `KANUNI_ADMIN_API_BASE_URL`,
  which defaults to `http://localhost:8000` and rarely needs changing
  locally).
- **Fills:** the `X-API-Key` header `kanuni ingest <folder> --source
  <id>` (`apps/ingestion/src/kanuni_ingest/cli.py`) sends to `POST
  /v1/admin/documents` and the other `/v1/admin/*` routes.
- **Setup:** same bootstrap as the frontend key below, but with `scopes =
  '{ingest:admin}'` instead of `'{query}'`.
- **Blocks:** bulk-ingesting real (non-fixture) documents via the CLI.

## Kanuni API key for the frontend (Phase 5)

- **Env vars:** `KANUNI_API_BASE_URL`, `KANUNI_API_KEY` (both server-only
  in `apps/web` — never `NEXT_PUBLIC_*`; see `.env.example`'s Phase 5
  section and `apps/web/src/lib/serverConfig.ts`).
- **Fills:** the `X-API-Key` header `apps/web`'s Route Handler proxies
  (`src/app/api/*/route.ts`) attach to every request they forward to
  `apps/api`. This is a *separate* key from `KANUNI_ADMIN_API_KEY`
  (Phase 1, used by the `kanuni ingest` CLI) — this one only needs the
  `query` scope, not `ingest:admin`.
- **Setup:**
  1. Insert a row into the `api_keys` table with `scopes = '{query}'` and
     `key_hash` set to the SHA-256 hex digest of a key you generate
     yourself (there is no key-issuing endpoint yet — see docs/PROGRESS.md's
     Phase 5 "Open ADR candidates" for why). A one-liner:
     `python3 -c "import hashlib,secrets; k=secrets.token_urlsafe(32); print(k); print(hashlib.sha256(k.encode()).hexdigest())"`
     — the first line is the key (put it in `.env`), the second is what
     goes in `key_hash`.
  2. Set `KANUNI_API_KEY=<the key, not the hash>` and
     `KANUNI_API_BASE_URL=http://localhost:8000` (or the deployed API's
     URL) in `apps/web`'s environment.
- **Blocks:** every page's data (`/` streaming answers, `/documents`
  listings, `/about`'s live document count) — without it, `apps/web`
  still builds and serves pages (verified in this sandbox), but every
  proxy route returns a 502 and the UI shows its designed error states
  rather than real data.

---

The items below (Phase 6, later revised post-handoff) are what's left to
actually go live: Supabase, Hugging Face Spaces, Vercel, GlitchTip, and
the GitHub Actions secrets/environment that tie them together.

## Supabase — Postgres + pgvector (staging & production)

- **Env var:** `DATABASE_URL` (bare, dbmate's own convention — matches
  `docker-compose.yml`'s local `migrate` service; also the GitHub Actions
  secret `deploy.yml`'s `migrate` job reads), separately set as
  `KANUNI_DATABASE_URL` on the Hugging Face Space for the running app
  (see the Hugging Face Spaces section below — the two names differ
  because dbmate and `Settings.database_url` read different, pre-existing
  conventions; not new to this phase).
- **Setup:**
  1. Create a project at https://supabase.com (free tier is enough to
     start; the pgvector extension is available by default).
  2. In the SQL editor, run `CREATE EXTENSION IF NOT EXISTS vector;` if
     it isn't already enabled.
  3. Project Settings → Database → Connection string (use the *pooled*
     connection string for the running app, the *direct* connection for
     running migrations — Supabase's pooler doesn't support all session
     features dbmate/asyncpg may need for DDL).
  4. Ideally, create two projects (or two databases in one project) for
     staging and production, so a staging incident/bad migration can't
     touch production data — the live setup below currently shares one
     project between both for simplicity (see `docs/PROGRESS.md`'s Open
     ADR candidates); splitting them later doesn't require a code change,
     just a second `DATABASE_URL`/`KANUNI_DATABASE_URL` pair.
- **Blocks:** everything that needs a real database — i.e., all of
  Phases 1–6's live verification, and the entire deploy pipeline
  (`deploy.yml`'s `migrate` job runs `dbmate up` against this before
  every deploy).
- **Status: live.** Connected and migrated against a real Supabase
  project (`infra/migrations/0001`–`0004`, including Row Level Security —
  see next item). `KANUNI_DATABASE_URL`/`DATABASE_URL` in `.env` point at
  it; verified with the app's actual `create_pool` connection code, not
  just a raw `psql` check.

### Row Level Security

Migrations `0003_enable_row_level_security.sql` and
`0004_enable_rls_on_schema_migrations.sql` enable RLS (zero policies) on
every table in the public schema — the 6 app tables (`documents`,
`chunks`, `document_relations`, `ingestion_jobs`, `api_keys`, `queries`)
plus `schema_migrations` (dbmate's own bookkeeping table — split into
its own migration since it isn't "app data," but it still lives in the
public schema and Supabase's advisor flags it identically).
Supabase's security advisor flags any public-schema table with RLS off,
since PostgREST/anon-key clients can read the schema directly the moment
they're ever exposed. Postgres exempts table owners from RLS by default
(we deliberately don't set `FORCE ROW LEVEL SECURITY`), and apps/api's
connection *is* the table owner (verified: `current_user` = `postgres`,
which owns every table) — so this closes the anon/PostgREST exposure
path with **zero effect on the app**, no code changes needed. If a table
ever needs direct client-side access (e.g. a future Storage/Realtime
integration querying `documents` straight from the browser instead of
through apps/api), add scoped policies for that table then — don't
disable RLS to work around it.

### Supabase Storage (document storage)

- **Env vars:** `SUPABASE_URL` (the project URL, e.g.
  `https://<ref>.supabase.co`), `SUPABASE_SERVICE_ROLE_KEY`, both bare
  (no `KANUNI_` prefix), shared verbatim between `apps/api` and
  `apps/ingestion` — see `.env.example`'s Phase 1 section.
- **Fills:** `SupabaseStorage` in
  `apps/api/src/kanuni_api/storage.py`/`apps/ingestion/src/kanuni_ingest/storage.py`
  (upload on admin document creation; read-back during ingestion's
  extraction/OCR stage). Replaced `LocalFilesystemStorage` + a Fly volume
  entirely (see `docs/PROGRESS.md`'s post-Phase-6 notes) — no local disk
  needed anymore, so there's nothing to provision on Fly for storage.
- **Setup:**
  1. Create a public bucket named `documents` (matches
     `Settings.storage_bucket`'s default) — either via the dashboard
     (Storage → New bucket → toggle "Public"), or by SQL against the
     project's own Postgres:
     ```sql
     INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
     VALUES ('documents', 'documents', true, 104857600, ARRAY['application/pdf']);
     ```
     Public is intentional, not a shortcut: Kanuni's corpus is public
     Bank of Tanzania regulatory text, and the whole point of Phase 5's
     citation side panel is a direct, shareable link to the source PDF
     page — a private bucket would need signed-URL generation for no
     real benefit here.
  2. Project Settings → API → copy the `service_role` key (**not** the
     `anon` key — uploads need to bypass bucket policies) into
     `SUPABASE_SERVICE_ROLE_KEY`. This key must never reach the browser;
     it's only ever read server-side (`apps/api`'s admin upload route,
     `apps/ingestion`'s worker).
  3. Set `SUPABASE_URL` to the same project URL used for the database
     connection.
- **Blocks:** document upload (`POST /v1/admin/documents`) and the
  citation side panel's "open source PDF" link — without these, an
  upload attempt fails with an unhandled 500 (`storage.write()`'s
  `httpx.HTTPStatusError` isn't specifically caught, so it falls through
  to the generic `internal_error` handler — worth a dedicated
  `StorageError` mapping if this needs a clearer client-facing error
  later), and existing citations simply omit the link
  (`ResolvedCitation.source_url` is `None`).

## Hugging Face Spaces — apps/api hosting (staging & production)

Chosen over Fly.io: Spaces' free CPU Docker tier has no time-boxed trial
(Fly's free allowance is limited and requires a card for anything past
it) — it runs indefinitely, sleeping after inactivity rather than
expiring. Tradeoff: cold starts after idle, and the free tier's RAM is
unconfirmed against bge-m3 + bge-reranker-v2-m3 running together (see
`docs/runbook.md`'s provider-outage section) — upgrade the Space's
hardware tier if `/readyz` or first-query latency looks OOM-y.

- **Env vars (GitHub secrets/variables):** `HF_TOKEN` (secret),
  `HF_USERNAME` (a **variable**, not a secret — it's public, it's part
  of the resulting URL; Settings → Secrets and variables → Actions →
  Variables tab).
- **Setup:**
  1. Sign up at https://huggingface.co.
  2. Settings → Access Tokens → create a token with **write** access
     (needed to push to your Spaces via git) → `HF_TOKEN` (GitHub Actions
     secret).
  3. Create two Spaces (Settings → New Space, or they're created
     automatically on first push by `infra/deploy/deploy_to_hf_space.sh`
     — either way, SDK must be **Docker**):
     - `kanuni-api-staging`
     - `kanuni-api`
  4. For each Space, Settings → Repository secrets, set:
     ```
     KANUNI_DATABASE_URL=<Supabase pooled connection string>
     GROQ_API_KEY=<from the Groq section above>
     SENTRY_DSN=<from the GlitchTip section below>
     SUPABASE_URL=<from the Supabase Storage section above>
     SUPABASE_SERVICE_ROLE_KEY=<from the Supabase Storage section above>
     ```
     `RELEASE_SHA` isn't set here — unlike Fly's `--env` flag,
     `deploy_to_hf_space.sh` has no scripted way to set a Space secret
     per-deploy (it only pushes code; see its header comment). It
     defaults to `"dev"` (`Settings.release_sha`), so GlitchTip events
     from this Space won't carry a real commit SHA until someone either
     updates this secret by hand after each deploy or the script is
     extended to call Hugging Face's API to set it automatically (a
     reasonable follow-up, not done here — see `docs/PROGRESS.md`'s Open
     ADR candidates).
     Staging and production should use *separate* Groq/GlitchTip keys
     where practical, so a staging incident can't exhaust a production
     quota — they currently share one Supabase database (see
     `docs/PROGRESS.md`'s Open ADR candidates for the tradeoff).
  5. `STAGING_API_KEY` / `PROD_API_KEY` (GitHub Actions secrets, read by
     `deploy.yml`'s smoke-test steps): a `query`-scoped Kanuni API key
     for each environment, bootstrapped the same way as the frontend key
     above, directly against the (shared) database.
  6. No volume/bucket to provision here — document storage is Supabase
     Storage (see above), not a local disk.
- **How deploys actually work:** `infra/deploy/deploy_to_hf_space.sh`
  builds a minimal bundle (the root `Dockerfile`, `apps/api`,
  `apps/ingestion`, `infra`, `packages`, and a generated Space
  `README.md` with the SDK frontmatter Hugging Face requires) and
  force-pushes it as a single commit to the Space's own git remote —
  it does **not** push this repo's full history. See that script's
  header comment and `docs/runbook.md`'s Deploying section for manual
  invocation / rollback.
- **Blocks:** the entire `deploy.yml` pipeline; live `apps/api` hosting.

## Vercel — apps/web hosting

No GitHub Actions job deploys this (see `docs/PROGRESS.md`'s Phase 6
notes for why) — Vercel's own Git integration is simpler and better at
this than a scripted equivalent would be.

- **Setup:**
  1. Sign up at https://vercel.com, "Add New Project," import this repo.
  2. Set the project's **Root Directory** to `apps/web` (monorepo
     support — Vercel detects the Next.js app there and ignores the rest).
  3. Framework preset: Next.js (auto-detected). Build command and output
     directory: leave as Vercel's Next.js defaults.
  4. Project Settings → Environment Variables, set for both Preview and
     Production (see `.env.example`'s Phase 5/6 sections for what each
     does):
     - `KANUNI_API_BASE_URL` — the corresponding Hugging Face Space's URL
       (`https://<your-hf-username>-kanuni-api-staging.hf.space` for
       Preview, `https://<your-hf-username>-kanuni-api.hf.space` for
       Production)
     - `KANUNI_API_KEY` — a `query`-scoped key for that environment
     - `NEXT_PUBLIC_SENTRY_DSN` — from the GlitchTip section below
     - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
       — the same values as `apps/web/.env.local` locally (Project
       Settings → API in Supabase — the *publishable* key, not
       `SUPABASE_SERVICE_ROLE_KEY`, which must never reach `apps/web` at
       all). Not read by any feature yet
       (`apps/web/src/lib/supabase/{client,server}.ts` are scaffolding
       for the next one that needs them — Auth, Realtime, or direct
       client-side Storage reads); safe to set now regardless, since
       these are meant to be public.
  5. Every push to `main` now deploys to Production automatically; every
     PR gets its own Preview deployment. `VERCEL_TOKEN` (already in
     `.env.example`) is only needed if you later want a CLI-driven
     deploy (`vercel deploy`) instead — not required for the dashboard
     flow above.
- **Blocks:** live `apps/web` hosting; the "Demo GIF / live demo link"
  placeholder in `README.md`.

## GlitchTip — error tracking (api, ingestion, web)

GlitchTip is an open-source reimplementation of Sentry's event-ingest
protocol — the default here instead of Sentry because its free hosted
tier isn't time-boxed the way Sentry's trial can be, and self-hosting is
a real option later if the free hosted quota ever gets tight. It's a
drop-in: `sentry-sdk` (Python) and `@sentry/nextjs` (web) don't know or
care which vendor's DSN they're pointed at, so the env var is still
named `SENTRY_DSN`/`NEXT_PUBLIC_SENTRY_DSN`, and switching to real
Sentry later (or for anyone who already has a Sentry account) is a
one-line DSN swap, nothing else — see `docs/runbook.md`'s error-triage
section.

- **Env vars:** `SENTRY_DSN` (server-side, all three services),
  `NEXT_PUBLIC_SENTRY_DSN` (browser-side, `apps/web` only — DSNs are
  meant to be public, this isn't a secret leak).
- **Setup:**
  1. Sign up at https://app.glitchtip.com (hosted free tier — no credit
     card), or self-host later via their published Docker image
     (`glitchtip/glitchtip`) if the free quota stops being enough.
  2. Create an organization, then a project.
  3. Project Settings → copy the DSN into `SENTRY_DSN` (Hugging Face
     Space repository secrets, see above) and `NEXT_PUBLIC_SENTRY_DSN`
     (Vercel env vars, see above).
- **Not wired up:** a CI release-creation step. Sentry's `sentry-cli` /
  `getsentry/action-release` call a release-management API that
  GlitchTip isn't confirmed to implement — rather than ship a step that
  might silently no-op or fail, `deploy.yml` doesn't include one. The
  part that actually matters for triage (every event tagged with
  `release`) still works via `sentry_sdk.init(release=...)` /
  `Sentry.init` at runtime — see the Hugging Face Spaces section above
  for `RELEASE_SHA`'s current limitation.
- **Blocks:** error visibility in production — the app runs and serves
  traffic fine without it (a blank DSN is the SDK's own documented
  no-op), you just won't see crashes anywhere but the Space's own logs /
  Vercel's function logs.

## GitHub Actions: secrets and environments

Repository secrets (Settings → Secrets and variables → Actions →
Repository secrets) — the complete set every workflow in this repo reads:

| Secret | Used by | Purpose |
|---|---|---|
| `GROQ_API_KEY` | `evals.yml` | answer-eval + judge model calls |
| `DATABASE_URL` | `deploy.yml` (`migrate` job) | runs `dbmate up` against Supabase directly from CI |
| `HF_TOKEN` | `deploy.yml` | git push auth to your Hugging Face Spaces |
| `STAGING_API_KEY` | `deploy.yml` | staging smoke test |
| `PROD_API_KEY` | `deploy.yml` | production smoke test |

Repository **variable** (same Settings page, "Variables" tab — not a
secret, since it's just your public HF username):

| Variable | Used by | Purpose |
|---|---|---|
| `HF_USERNAME` | `deploy.yml` | constructs the Space git remote and its public `.hf.space` URL |

`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`KANUNI_DATABASE_URL` aren't
GitHub Actions secrets at all — they're Hugging Face Space repository
secrets (see the Hugging Face Spaces section above), since only the
running app (not the CI runner) needs them; the `migrate` job in
`deploy.yml` is the one exception that touches Supabase directly from
CI, using its own `DATABASE_URL` secret above.

Repository environment (Settings → Environments → New environment,
named exactly `production`):

- Add required reviewers under "Deployment protection rules" — this is
  §12's manual approval gate. `deploy.yml`'s `deploy-production` job
  references `environment: production` and will not run until an
  approver approves it in the Actions UI.
- Optionally restrict which branches can deploy to this environment to
  `main`.
