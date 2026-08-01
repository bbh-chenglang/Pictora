#!/usr/bin/env bash

set -Eeuo pipefail

COMPOSE_FILE="compose.v1.yaml"
PROJECT_NAME="genimage-v1"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or is not available in PATH." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required." >&2
    exit 1
fi

docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" config --quiet
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --build --wait --wait-timeout 180
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" ps

echo "GenImage v1 is available at http://127.0.0.1:9001/"
