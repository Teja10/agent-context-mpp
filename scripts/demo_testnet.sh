#!/usr/bin/env bash
set -euo pipefail

CONTEXT_URL="http://127.0.0.1:8000/articles/ai-agent-payments/context"

command -v curl >/dev/null || { echo "missing required command: curl" >&2; exit 1; }
command -v tempo >/dev/null || { echo "missing required command: tempo" >&2; exit 1; }

echo "1. tempo wallet whoami"
tempo wallet whoami

echo "2. curl -v \"\$CONTEXT_URL\""
curl -v "$CONTEXT_URL"

echo "3. tempo request GET \"\$CONTEXT_URL\""
tempo request GET "$CONTEXT_URL"
