#!/usr/bin/env bash
# Ship the reader to https://singularitynexus.nl/books.
#
#   cp deploy/deploy.env.example deploy/deploy.env   # once, then edit
#   ./deploy/deploy.sh                               # every time after
#   ./deploy/deploy.sh --dry-run                     # show what would change
#
# What this does, and the three things it deliberately does not.
#
# It builds the frontend with PUBLIC_BASE so every asset URL carries the /books prefix,
# then rsyncs the code and the built bundle to the server and restarts the service.
#
#   * **It never sends secrets.** `.env` is not in the release. The server reads its own
#     keys from an EnvironmentFile outside the release directory (see bookv3.service),
#     so a deploy cannot overwrite them and a leaked release tarball carries no key.
#   * **It never touches `data/`.** Profiles, PINs, device tokens, reading positions and
#     the Hardcover cache are the *server's* state and only exist there. Syncing this
#     machine's copy over them would hand the live app a laptop's idea of who has read
#     what — and `--delete` would remove what it does not know about.
#   * **It never deletes books.** Code syncs with `--delete` so a renamed module does not
#     linger; `books/` syncs without it, because a book ingested on the server is not in
#     this checkout and is not stale — it is the point of the app.
#
# Run it from anywhere; it locates the repository itself.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"

DRY_RUN=""
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN="--dry-run"
  echo "DRY RUN — nothing will be written on the server."
  echo
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

if [ ! -f "$HERE/deploy.env" ]; then
  echo "error: deploy/deploy.env is missing." >&2
  echo "       cp deploy/deploy.env.example deploy/deploy.env and fill it in." >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a; . "$HERE/deploy.env"; set +a

: "${PUBLIC_BASE:?set PUBLIC_BASE in deploy/deploy.env}"
: "${DEPLOY_HOST:?set DEPLOY_HOST in deploy/deploy.env}"
: "${DEPLOY_USER:?set DEPLOY_USER in deploy/deploy.env}"
: "${DEPLOY_PATH:?set DEPLOY_PATH in deploy/deploy.env}"

case "$PUBLIC_BASE" in
  */) ;;
  # Vite joins base to filenames without inserting one, so a missing slash silently
  # produces /booksassets/index.js and a blank page. Cheaper to catch here.
  *) echo "error: PUBLIC_BASE must end in a slash (got '$PUBLIC_BASE')." >&2; exit 1 ;;
esac

TARGET="$DEPLOY_USER@$DEPLOY_HOST"

echo "repository : $ROOT"
echo "target     : $TARGET:$DEPLOY_PATH"
echo "base path  : $PUBLIC_BASE"
echo

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

echo "==> building the frontend"
if [ ! -d web/node_modules ]; then
  (cd web && npm ci)
fi
(cd web && PUBLIC_BASE="$PUBLIC_BASE" npm run build)

# The bundle is useless if the prefix did not take, and the failure is a blank page with
# 404s in the console rather than an error anyone sees here. Check before shipping.
EXPECT="${PUBLIC_BASE}assets/"
if ! grep -q "$EXPECT" web/dist/index.html; then
  echo "error: built index.html does not reference $EXPECT — PUBLIC_BASE did not apply." >&2
  echo "       (on Windows, run this from Git Bash with MSYS_NO_PATHCONV=1)" >&2
  exit 1
fi
echo "    assets are served from $EXPECT"
echo

# ---------------------------------------------------------------------------
# Ship
# ---------------------------------------------------------------------------

# The application, minus everything that is either this machine's or the server's.
# `books/` is excluded here and synced separately below, under different rules.
CODE_EXCLUDES=(
  --exclude '.git'
  --exclude '.env'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude 'data'          # the server's own state — see the header
  --exclude 'books'         # synced separately, without --delete
  --exclude 'next'          # local ingest inbox
  --exclude 'pdfs'          # local source PDFs, large and not needed to serve
  --exclude 'uploaded_files'
  --exclude 'web/node_modules'
  --exclude 'web/src'       # the bundle is built; the source is not needed to run
  --exclude 'deploy/deploy.env'
  --exclude '.claude'
)

echo "==> syncing code and bundle"
rsync -az --delete $DRY_RUN "${CODE_EXCLUDES[@]}" \
  --include 'web/' --include 'web/dist/***' --exclude 'web/*' \
  ./ "$TARGET:$DEPLOY_PATH/"

echo "==> syncing books (additive — nothing on the server is removed)"
rsync -az $DRY_RUN ./books/ "$TARGET:$DEPLOY_PATH/books/"

if [ -n "$DRY_RUN" ]; then
  echo
  echo "dry run complete — no service was restarted."
  exit 0
fi

# ---------------------------------------------------------------------------
# Install and restart
# ---------------------------------------------------------------------------

echo
echo "==> installing dependencies and restarting"
ssh "$TARGET" bash -s <<REMOTE
set -euo pipefail
cd "$DEPLOY_PATH"

# The data directory is created, never synced: the app writes profiles, positions and
# its Hardcover cache here and they must survive every deploy.
mkdir -p data/positions data/partials

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

if [ -n "${DEPLOY_SERVICE:-}" ]; then
  sudo systemctl restart "${DEPLOY_SERVICE}"
  sleep 2
  systemctl is-active --quiet "${DEPLOY_SERVICE}" \
    && echo "    ${DEPLOY_SERVICE} is running" \
    || { echo "    ${DEPLOY_SERVICE} did NOT come back up"; journalctl -u "${DEPLOY_SERVICE}" -n 30 --no-pager; exit 1; }
else
  echo "    DEPLOY_SERVICE is empty — skipping restart (install the unit first)"
fi
REMOTE

echo
echo "==> checking the live site"
if curl -fsS -o /dev/null -w '    %{http_code}  %{url_effective}\n' \
     "https://$DEPLOY_HOST${PUBLIC_BASE}api/shelf"; then
  echo "done."
else
  echo "    the shelf did not answer — check nginx and the service." >&2
  exit 1
fi
