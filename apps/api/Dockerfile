# Build context is the repo root (uv workspace) — see docker-compose.yml.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /workspace
COPY . .
RUN uv sync --all-packages

WORKDIR /workspace/apps/api
EXPOSE 8000

CMD ["uv", "run", "--project", "/workspace/apps/api", "uvicorn", "kanuni_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/workspace/apps/api/src"]
