#!/usr/bin/env bash
# Run the reader in development: FastAPI on :8001, Vite on :5173 with /api proxied.
# Open http://localhost:5173. For the production shape instead, run `./build.sh`
# and open http://localhost:8001, where the API serves the built bundle itself.
#
# 8001, not 8000: an unrelated service holds 8000 on the main dev machine. The number
# matters to nothing here except that vite.config.js names the same one, so both read
# API_PORT and default together.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d web/node_modules ]; then
  echo "installing frontend dependencies..."
  (cd web && npm install)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

uvicorn api.main:app --reload --port "${API_PORT:-8001}" &
(cd web && API_PORT="${API_PORT:-8001}" npm run dev) &

wait
