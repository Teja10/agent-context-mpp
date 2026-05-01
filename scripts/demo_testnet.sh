#!/usr/bin/env bash
set -euo pipefail

HEALTH_URL="http://127.0.0.1:8000/health"
ARTICLES_URL="http://127.0.0.1:8000/articles"

command -v curl >/dev/null || { echo "missing required command: curl" >&2; exit 1; }
command -v tempo >/dev/null || { echo "missing required command: tempo" >&2; exit 1; }

echo "1. tempo wallet whoami"
tempo wallet whoami

echo "2. curl -fsS \"\$HEALTH_URL\""
curl -fsS "$HEALTH_URL"

echo "3. curl -fsS \"\$ARTICLES_URL\""
curl -fsS "$ARTICLES_URL"

echo "Article payment demo requires future publisher/article APIs to create rows."
