#!/usr/bin/env bash
# Build the reader frontend into web/dist, which api/main.py serves at :8001.
set -euo pipefail

cd "$(dirname "$0")/web"

if [ ! -d node_modules ]; then
  npm install
fi

npm run build

echo
echo "Built web/dist. Serve it with:"
echo "  uvicorn api.main:app --port 8001   # then open http://localhost:8001"
