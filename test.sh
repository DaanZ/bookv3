#!/usr/bin/env bash
# Run every test in the repo: the Python helpers and the reading model.
#
# Neither half needs a dependency that is not already here — unittest is stdlib and
# node:test is built in — so this works on a clean checkout with no API key.
set -euo pipefail

cd "$(dirname "$0")"

echo "── python ──"
python3 -m unittest discover -s tests "$@"

echo
echo "── javascript ──"
cd web
if [ ! -d node_modules ]; then
  npm install
fi
npm test --silent
