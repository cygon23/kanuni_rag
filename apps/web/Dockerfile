# Build context is the repo root (bun workspace) — see docker-compose.yml.
FROM oven/bun:1

WORKDIR /workspace
COPY . .
RUN bun install --frozen-lockfile

WORKDIR /workspace/apps/web
EXPOSE 3000

CMD ["bun", "run", "dev"]
