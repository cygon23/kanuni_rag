#!/usr/bin/env bash
# Pushes a minimal deploy bundle to a Hugging Face Space (Docker SDK).
#
# A Space is its own git repo, and Docker-SDK Spaces require a file
# literally named `Dockerfile` plus a `README.md` with specific YAML
# frontmatter at the repo root (see docs/NEEDS.md's Hugging Face Spaces
# section). Rather than push this whole monorepo's history (and fight
# our real README.md for that frontmatter slot), this builds a small,
# throwaway bundle — just the source the image needs, the root
# Dockerfile, and a generated Space README — and force-pushes it as a
# single commit. The Space's own git history is intentionally not
# preserved across deploys; the source of truth is this repo.
#
# Usage: deploy_to_hf_space.sh <space-name> <title>
# Required env: HF_USERNAME, HF_TOKEN

set -euo pipefail

SPACE_NAME="$1"
TITLE="$2"

: "${HF_USERNAME:?HF_USERNAME env var is required}"
: "${HF_TOKEN:?HF_TOKEN env var is required}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUNDLE_DIR="$(mktemp -d)"
trap 'rm -rf "$BUNDLE_DIR"' EXIT

cp -r "$REPO_ROOT/apps" "$BUNDLE_DIR/apps"
cp -r "$REPO_ROOT/infra" "$BUNDLE_DIR/infra"
cp -r "$REPO_ROOT/packages" "$BUNDLE_DIR/packages"
cp "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/uv.lock" "$BUNDLE_DIR/"
cp "$REPO_ROOT/Dockerfile" "$BUNDLE_DIR/Dockerfile"

# apps/web isn't needed on this Space (it deploys to Vercel separately)
# and only bloats the image — drop it from the bundle.
rm -rf "$BUNDLE_DIR/apps/web"

cat > "$BUNDLE_DIR/README.md" <<EOF
---
title: ${TITLE}
emoji: ⚖️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

Kanuni API — deployed automatically from
https://github.com/${GITHUB_REPOSITORY:-<this repo>} by .github/workflows/deploy.yml.
Not meant to be edited directly on Hugging Face; changes here are
overwritten on the next deploy.
EOF

cd "$BUNDLE_DIR"
git init -q
git config user.email "deploy@kanuni.dev"
git config user.name "Kanuni Deploy Bot"
git add -A
git commit -q -m "Deploy ${GITHUB_SHA:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
git remote add space "https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}"
git push --force space HEAD:main

echo "Deployed to https://${HF_USERNAME,,}-${SPACE_NAME,,}.hf.space"
