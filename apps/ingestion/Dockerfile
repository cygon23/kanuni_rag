# Build context is the repo root (uv workspace) — see docker-compose.yml.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /workspace
COPY . .
RUN uv sync --all-packages

WORKDIR /workspace/apps/ingestion

CMD ["uv", "run", "--project", "/workspace/apps/ingestion", "python", "-m", "kanuni_ingest"]
