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

resolve_app_version() {
    if [[ -n "${APP_VERSION:-}" ]]; then
        printf '%s' "$APP_VERSION"
        return
    fi

    local version branch
    version="$(git describe --tags --exact-match 2>/dev/null || true)"
    if [[ "$version" =~ ^V[0-9]+$ ]]; then
        printf '%s' "$version"
        return
    fi

    branch="$(git branch --show-current 2>/dev/null || true)"
    if [[ "$branch" =~ ^V[0-9]+$ ]]; then
        printf '%s' "$branch"
        return
    fi

    printf 'dev'
}

APP_VERSION="$(resolve_app_version)"
export APP_VERSION

docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 180
docker compose ps

echo "Pictora is available at http://127.0.0.1:8083/ (version ${APP_VERSION})"
