# 0001. Use bun, not pnpm, for JS package management

## Context

PROJECT_SPEC.md §2 originally locked `pnpm` as the JS package manager for
`apps/web` and `packages/shared`. During Phase 0 scaffolding, generating
`pnpm-lock.yaml` repeatedly failed: the npm registry connection available at
the time timed out fetching large package metadata (e.g. `@types/node`'s
full version history, ~11MB), both in the sandbox this repo was scaffolded
in and — per the `ERR_PNPM_NO_LOCKFILE` failures seen in an early CI run and
local `make setup` run — the lockfile was never actually generated and
committed, so every `pnpm install --frozen-lockfile` had nothing to check
against and failed immediately.

A one-off `bun install` completed the same dependency set in well under a
minute against the same network conditions.

## Decision

Use `bun` as the sole JS package manager and script runner for the
workspace (`apps/web`, `packages/shared`), replacing `pnpm` everywhere:

- `bun.lock` is the committed lockfile (`pnpm-lock.yaml` / `pnpm-workspace.yaml` removed).
- Workspaces are declared via the standard npm-style `"workspaces"` field in
  the root `package.json`, not `pnpm-workspace.yaml`.
- `Makefile`, `.github/workflows/ci.yml`, and `apps/web/Dockerfile` all use
  `bun install` / `bun run --filter <pkg> <script>` / `bun audit`.
- CI sets up the toolchain via `oven-sh/setup-bun@v2` instead of
  `pnpm/action-setup@v4` + `actions/setup-node@v4`.

## Alternatives considered

- **Keep pnpm, just retry harder.** Rejected: the underlying registry
  latency isn't something this repo's tooling controls, and it produced two
  separate real failures (a stalled sandbox install, and a missing-lockfile
  CI/local failure) before this was raised. bun proved reliable under the
  same conditions.
- **npm.** Not evaluated in depth — bun was already proven to work in this
  environment and offers a single static binary with no separate Node
  version coupling for the package manager itself (relevant since a
  Node-20-vs-22 mismatch was a second, independent issue hit during setup).
- **Mixed: bun locally, pnpm in CI/committed lockfile.** Rejected as
  inconsistent — different tools resolving the same `package.json` can
  produce different dependency trees, defeating the point of a committed
  lockfile.

## Consequences

- Contributors need `bun` installed locally (`curl -fsSL https://bun.sh/install | bash`
  or equivalent) instead of `pnpm`/corepack.
- `apps/api` and `apps/ingestion` are unaffected — they use `uv`/Python and
  never depended on pnpm.
- Bun is largely Node-compatible for running Next.js, but is a different
  runtime than Node; if a subtle Next.js/Node-API incompatibility surfaces
  later, that's a new, separate problem to solve within bun — not a reason
  to revisit this decision (see project memory on this).
