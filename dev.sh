#!/usr/bin/env bash
# Run the reader in development: FastAPI on :8000, Vite on :5173 with /api proxied.
# Open http://localhost:5173. For the production shape instead, run `./build.sh`
# and open http://localhost:8000, where the API serves the built bundle itself.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d web/node_modules ]; then
  echo "installing frontend dependencies..."
  (cd web && npm install)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

uvicorn api.main:app --reload --port 8000 &
(cd web && npm run dev) &

wait
