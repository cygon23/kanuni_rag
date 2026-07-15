.PHONY: setup dev down test lint format eval migrate openapi

setup: ## Install Python (uv) and JS (bun) dependencies for a fresh clone.
	test -f .env || cp .env.example .env
	uv sync --all-packages
	bun install --frozen-lockfile

dev: ## Bring up the full local stack (db, api, ingestion, web).
	docker compose up --build

down: ## Tear down the local stack and its volumes.
	docker compose down -v

test: ## Run Python and frontend test suites.
	uv run pytest
	bun run --filter kanuni-web test

lint: ## Run all linters/formatters/type-checkers in check mode.
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	bun run --filter kanuni-web lint
	bun run --filter kanuni-web typecheck
	bun run --filter kanuni-web format:check

eval: ## Ingest the fixture corpus, run the full eval suite, and write a report.
	uv run python evals/prepare_eval_corpus.py
	uv run python evals/run_retrieval_eval.py --golden evals/golden/qa.jsonl --output evals/reports/retrieval-results.json
	uv run python evals/run_answer_eval.py --golden evals/golden/qa.jsonl --output evals/reports/answer-results.json
	uv run python evals/report.py --retrieval-results evals/reports/retrieval-results.json --answer-results evals/reports/answer-results.json

migrate: ## Apply pending database migrations with dbmate.
	dbmate --migrations-dir infra/migrations up

openapi: ## Regenerate packages/shared's TypeScript types from the API's OpenAPI schema.
	uv run python apps/api/scripts/export_openapi_schema.py packages/shared/src/generated/openapi-schema.json
	bun run --filter @kanuni/shared generate
