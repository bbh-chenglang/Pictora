#!/usr/bin/env bash

set -Eeuo pipefail

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or is not available in PATH." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required." >&2
    exit 1
fi

docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
docker compose ps

echo "GenImage is available at http://127.0.0.1:8083/"
