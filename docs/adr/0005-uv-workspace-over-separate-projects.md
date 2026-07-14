# 0005. A single uv workspace for `apps/api` and `apps/ingestion`, not two independent projects

## Context

PROJECT_SPEC.md §3 defines `apps/api` and `apps/ingestion` as two separately
deployable Python services (§5: "Two deployable services ... They share the
DB and the `shared` package only — no direct service-to-service calls in
v1"). §2 locks `uv` as the Python package manager. Nothing in the spec
mandates whether they should be one workspace or two fully independent
`uv` projects with separate lockfiles.

## Decision

A single root `pyproject.toml` declares a `uv` workspace
(`[tool.uv.workspace] members = ["apps/api", "apps/ingestion"]`) with one
shared lockfile (`uv.lock`) and one shared dev-tool configuration
(`ruff`, `mypy --strict`, `pytest`) at the root. Each app keeps its own
`pyproject.toml` declaring only its own runtime dependencies and remains
independently deployable (each Dockerfile installs only what it needs via
`uv sync`).

## Alternatives considered

- **Two fully independent `uv` projects**, each with its own lockfile and
  lint/type-check config. Rejected: it would mean running `ruff`/`mypy`
  twice with two configs to keep in sync, and two lockfiles that could
  drift on shared transitive dependencies (e.g. `pydantic`, `structlog`)
  with no mechanism forcing them to agree — a correctness risk for a
  "share the DB, not the code" architecture that already asks contributors
  to reason about two codebases.
- **Merge them into a single deployable package.** Rejected outright: it
  directly contradicts §5's two-services architecture and would make
  "deploy the ingestion worker without redeploying the API" impossible.

## Consequences

- `make setup` / `uv sync --all-packages` installs both services' Python
  dependencies in one pass, and `uv run mypy` / `uv run pytest` type-check
  and test both from one invocation and one config (`pyproject.toml`
  `[tool.mypy]`, `[tool.pytest.ini_options]`).
- A dependency version bump for a package used by both services updates
  once, in one lockfile — there is no scenario where `apps/api` and
  `apps/ingestion` silently resolve different versions of the same
  transitive dependency.
- Each service's Docker image still only ships its own dependencies:
  `apps/api/Dockerfile` and `apps/ingestion/Dockerfile` each run
  `uv sync` scoped to their own `pyproject.toml`, so the workspace
  structure is purely a development/CI convenience, not a deployment
  coupling.
