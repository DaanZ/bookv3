"""The reader's backend.

Streamlit still owns ingest (`app.py`, `prep.py`); this serves the reading surface —
the shelf, a book's parts, reading position, and finishing a book. It reads the same
`books/*.json` the pipeline writes, and adds nothing to that format.

    uvicorn api.main:app --reload --port 8001

This file is the app and nothing else: middleware, the routers, and the built frontend.
The routes live in `api/routes/`, one module per area, and who may call them is decided
in `api/deps.py` — `reader` and `admin`, the whole permission model in one place.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import collection, hardcover, ingest, profiles, reading, session

# The reader itself needs no key, but this process reports whether one is present and
# reads OPENROUTER_MODEL for the default estimate. Nothing else here loads .env: the
# pipeline's own load_dotenv lives behind an import the API deliberately does not make.
load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIST = os.path.join(ROOT, "web", "dist")

app = FastAPI(title="bookv3 reader", version="1.0.0")

# Vite's dev server runs on another port; the built app is served from this one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store_api(request, call_next):
    """API answers are never cacheable.

    Without this the browser is free to keep one, and it did: a stale server briefly
    answered /api/profiles with the SPA's index.html, the browser cached that under a
    200, and every reload afterwards was served HTML from cache while curl saw correct
    JSON from the same URL. The app reported "Unexpected token '<'" and read as a guest
    with no history, long after the server was fixed.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# In the order they were written in, when this was one file. No two of them claim the
# same method and path, so the order does not decide anything today — but the SPA
# fallback below must stay after all of them.
for area in (session, profiles, reading, hardcover, collection, ingest):
    app.include_router(area.router)


# The built frontend, when there is one. Mounted last so /api always wins.
if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")

    # The ambience beds. Mounted explicitly rather than left to the SPA fallback so
    # they are served with Range support — Safari will not play audio without it.
    ambience_dir = os.path.join(WEB_DIST, "ambience")
    if os.path.isdir(ambience_dir):
        app.mount("/ambience", StaticFiles(directory=ambience_dir), name="ambience")

    _DIST_ROOT = os.path.realpath(WEB_DIST)

    @app.get("/{path:path}")
    def spa(path: str):
        index = os.path.join(_DIST_ROOT, "index.html")
        if not path:
            return FileResponse(index)

        # Resolve first, then check the result is still inside web/dist. Joining the
        # URL straight onto the directory would hand out any file the process can read
        # given enough "../" — Starlette normalises the path before it reaches here, so
        # this is not reachable today, but that is its behaviour, not our guarantee.
        candidate = os.path.realpath(os.path.join(_DIST_ROOT, path))
        inside = candidate == _DIST_ROOT or candidate.startswith(_DIST_ROOT + os.sep)
        if inside and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index)
