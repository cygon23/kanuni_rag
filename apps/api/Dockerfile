# Build context is the repo root (uv workspace) — see docker-compose.yml
# and the root-level Dockerfile (identical content, required by Hugging
# Face Spaces' Docker SDK convention — see that file's header comment).
# This is the production image; docker-compose.yml's `api` service adds
# --reload back via a `command:` override for local dev, rather than
# this image baking in a dev-only flag. Migrations run as their own
# deploy.yml step (dbmate against Supabase directly), not from inside
# this image — Hugging Face Spaces has no Fly-style pre-deploy release
# hook to run them from.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /workspace
COPY . .
RUN uv sync --all-packages

WORKDIR /workspace/apps/api
EXPOSE 8000

CMD ["uv", "run", "--project", "/workspace/apps/api", "uvicorn", "kanuni_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
