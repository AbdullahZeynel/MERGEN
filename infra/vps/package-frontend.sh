#!/usr/bin/env bash
# Build on the development machine, not on the VPS. Never uploads anything.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$#" -ne 0 ]]; then
    echo 'Usage: bash infra/vps/package-frontend.sh (demo data is deployed separately to MCP)' >&2
    exit 2
fi
cd "$repo_dir/frontend"
npm ci
npm run check
mkdir -p "$repo_dir/.local/releases"
release_id="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD)"
artifact="$repo_dir/.local/releases/frontend-$release_id.tar.gz"
if [[ -e "$artifact" ]]; then
    echo 'Artifact already exists; retry with a new timestamp.' >&2
    exit 1
fi
tar --exclude='./demo' -czf "$artifact" -C dist .
sha256sum "$artifact"
echo "Package ready: $artifact"
echo 'No upload or deployment performed. Supply the SHA-256 to deploy_frontend.py.'
