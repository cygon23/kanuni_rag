# Contributing to Kanuni

## Ground rules

- Read [PROJECT_SPEC.md](PROJECT_SPEC.md) first. It is the single source of
  truth; all code must conform to it. If a decision isn't covered there,
  follow the Engineering Standards (§4) and record the decision as an ADR
  (see [docs/adr/](docs/adr/), §15).
- Build phases are executed in order (§14) and each phase ends with green CI.
  Please don't jump ahead of the current phase in a PR.

## Local setup

```bash
make setup
make dev
```

## Before opening a PR

```bash
make lint    # ruff + eslint + prettier --check
make test    # pytest (api, ingestion) + frontend tests
```

Both must pass locally; CI enforces the same checks (`.github/workflows/ci.yml`).

## Code standards

- Python: fully typed, `ruff` clean, `mypy --strict` clean. Google-style
  docstrings on public functions/classes.
- TypeScript: `strict: true`, ESLint clean, Prettier formatted.
- Routes contain no business logic; services contain no SQL; all SQL lives in
  `db/` repositories. See §3 and §4 of the spec for the full rules.
- No file over ~400 lines, no function over ~50 lines without justification.
- No dead code, no commented-out code, no TODOs without a linked issue.

## Commit / PR conventions

- Keep PRs scoped to one phase or one concern.
- Describe *why*, not just *what*, in the PR description — the diff already
  shows what changed.
- If your change touches `retrieval/`, `generation/`, `prompts/`, or chunking,
  the eval suite runs automatically and posts a metrics diff — investigate
  any regression before merging.

## Reporting issues

Use GitHub Issues for bugs and feature requests. For security
vulnerabilities, do not open a public issue — see [SECURITY.md](SECURITY.md).
