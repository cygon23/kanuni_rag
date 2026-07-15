# Hugging Face Spaces' Docker SDK requires a file literally named
# `Dockerfile` at the repository root — this is that file, and its
# content must be kept in sync with apps/api/Dockerfile by hand (Docker
# has no native "include another Dockerfile" directive). Everything else
# (docker-compose.yml, local `docker build`) keeps using
# apps/api/Dockerfile directly, unaffected by this file.
#
# .github/workflows/deploy.yml builds a minimal deploy bundle (this
# Dockerfile + the source dirs it needs + a Space-specific README.md
# frontmatter) rather than pushing the whole monorepo — see that
# workflow and docs/NEEDS.md's Hugging Face Spaces section.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /workspace
COPY . .
RUN uv sync --all-packages

WORKDIR /workspace/apps/api
EXPOSE 8000

CMD ["uv", "run", "--project", "/workspace/apps/api", "uvicorn", "kanuni_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
