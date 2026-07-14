# Build context is the repo root (pnpm workspace) — see docker-compose.yml.
FROM node:20-slim

RUN corepack enable

WORKDIR /workspace
COPY . .
RUN pnpm install --frozen-lockfile

WORKDIR /workspace/apps/web
EXPOSE 3000

CMD ["pnpm", "dev"]
