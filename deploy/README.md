# Deploying to singularitynexus.nl/books

The reader is one process: FastAPI serves the API *and* the built frontend, so there is
no separate static host and nothing to keep in sync between two of them. nginx puts it
under `/books` on a domain that already has a site on it.

There is no CI here and there is not going to be. The build and the checks run on this
machine before a push, and `deploy.sh` runs them again before it ships anything.

## Once, on the server

```bash
sudo mkdir -p /srv/bookv3 /etc/bookv3
sudo chown deploy:deploy /srv/bookv3

# The keys. Never in the release directory, so a deploy cannot overwrite them.
sudo install -m 600 /dev/null /etc/bookv3/bookv3.env
sudo nano /etc/bookv3/bookv3.env
#   OPENROUTER_API_KEY=sk-or-v1-...
#   HARDCOVER_API_KEY=...            # optional; without it the Hardcover features idle

sudo cp bookv3.service.example /etc/systemd/system/bookv3.service   # edit paths/user
sudo systemctl daemon-reload
```

Then paste `nginx-books.conf.example` inside the existing `server` block for
singularitynexus.nl, and `sudo nginx -t && sudo systemctl reload nginx`.

## Once, on this machine

```bash
cp deploy/deploy.env.example deploy/deploy.env   # then edit; it is gitignored
```

## Every time

```bash
./deploy/deploy.sh --dry-run   # shows exactly what would change on the server
./deploy/deploy.sh
```

The script builds the frontend with `PUBLIC_BASE=/books/`, refuses to ship if the prefix
did not take, syncs, installs, restarts, and finishes by asking the live site for
`/books/api/shelf`. A non-200 there fails the deploy loudly rather than leaving you to
discover it.

## What is not sent, and why

| Not sent | Because |
| --- | --- |
| `.env` | The server reads `/etc/bookv3/bookv3.env`, which no deploy touches. |
| `data/` | Profiles, PINs, device tokens, positions and the Hardcover cache are the *server's* state. Syncing this laptop's copy over them would replace who has read what. |
| `pdfs/`, `next/` | Source PDFs. Large, and not needed to serve a summary. |
| `web/src`, `node_modules` | The bundle is built here; the source is not needed to run. |

`books/` **is** sent, but additively — `rsync` without `--delete` — because a book
ingested on the server is not in this checkout and is not stale.

## The subpath, and the one thing that breaks it

Nothing in the app hardcodes `/` any more. `web/src/lib/base.js` reads
`import.meta.env.BASE_URL`, which Vite fills from `base` at build time, and the API base,
the upload paths, the four ambience beds and the favicons all derive from it. The
manifest uses relative URLs so it needs no templating at all.

The thing that breaks it is a mismatch: the nginx `location` and `PUBLIC_BASE` must name
the same prefix, and `proxy_pass` must keep its trailing slash so nginx strips `/books`
before FastAPI sees the path. Change one without the other and every asset 404s on a
blank page.

## Running it from Windows

`deploy.sh` needs bash — use Git Bash. One wrinkle: Git Bash rewrites values that look
like absolute paths, so `PUBLIC_BASE=/books/` can arrive as `C:/Program Files/Git/books/`
and produce a bundle pointing at nonsense. The script checks the built `index.html` for
the expected prefix and refuses to ship if it is wrong; if you hit it, prefix the command
with `MSYS_NO_PATHCONV=1`.
