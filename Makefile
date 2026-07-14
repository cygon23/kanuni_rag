.PHONY: setup dev down test lint format eval migrate

setup: ## Install Python (uv) and JS (pnpm) dependencies for a fresh clone.
	test -f .env || cp .env.example .env
	uv sync --all-packages
	pnpm install --frozen-lockfile

dev: ## Bring up the full local stack (db, api, ingestion, web).
	docker compose up --build

down: ## Tear down the local stack and its volumes.
	docker compose down -v

test: ## Run Python and frontend test suites.
	uv run pytest
	pnpm --filter kanuni-web test

lint: ## Run all linters/formatters/type-checkers in check mode.
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm --filter kanuni-web lint
	pnpm --filter kanuni-web exec prettier --check .

eval: ## Run the retrieval + answer evaluation suite and write a report.
	uv run python evals/run_retrieval_eval.py
	uv run python evals/run_answer_eval.py
	uv run python evals/report.py

migrate: ## Apply pending database migrations with dbmate.
	dbmate --migrations-dir infra/migrations up
