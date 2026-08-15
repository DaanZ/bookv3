"""The reader's backend.

Streamlit still owns ingest (`app.py`, `prep.py`); this serves the reading surface —
the shelf, a book's parts, reading position, and finishing a book. It reads the same
`books/*.json` the pipeline writes, and adds nothing to that format.

    uvicorn api.main:app --reload --port 8000
"""

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import enrich, jobs, library, positions
from hardcover.request import mark_book_as_read

# A book PDF; anything larger than this is very unlikely to be one.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

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


class PositionIn(BaseModel):
    part: int = Field(ge=0)
    page: int = Field(ge=0)


class MoveIn(BaseModel):
    finished: bool


@app.get("/api/shelf")
def get_shelf():
    books = library.shelf()

    # Anything never looked up goes to the enrichment worker — books ingested before
    # this existed, and books written by prep.py, which never goes through the API.
    # It returns immediately; the requests happen one at a time on another thread.
    enrich.queue_missing(books)

    return {
        "books": books,
        "counts": {
            "total": len(books),
            "read": sum(1 for b in books if b["state"] == "read"),
        },
    }


@app.get("/api/enrichment")
def get_enrichment():
    """How far the background cover pass has got. The library screen shows this so an
    automatic thing is a visible thing, rather than covers appearing for no reason."""
    return enrich.summary(total=len(library.index()))


@app.get("/api/covers/{key}")
def get_cover(key: str):
    """The stored jacket. `enrich.cover_path` resolves the name from our own store and
    refuses anything that lands outside data/covers, so the key never becomes a path."""
    path = enrich.cover_path(key)
    if path is None:
        raise HTTPException(status_code=404, detail="No cover for that book.")
    return FileResponse(path, headers={"cache-control": "public, max-age=3600"})


@app.get("/api/books/{key}")
def get_book(key: str):
    detail = library.book(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")
    return detail


@app.put("/api/books/{key}/position")
def put_position(key: str, body: PositionIn):
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_position(key, body.part, body.page)


@app.delete("/api/books/{key}/position")
def delete_position(key: str):
    """Start a book again from the beginning."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(key)
    return {"ok": True}


@app.post("/api/books/{key}/finish")
def finish_book(key: str):
    """Mark read on Hardcover, then move the JSON available -> read.

    The move happens either way — the book *was* read — but `markedRead` only comes
    back true when Hardcover actually accepted it, so the finish screen never paints
    the green chip on a failed call.
    """
    detail = library.book(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    already_read = detail["state"] == "read"
    result = mark_book_as_read(detail["fullTitle"], detail["author"])
    marked = "error" not in result

    moved = None if already_read else library.move_to_read(key)
    positions.save_position(key, max(0, detail["partCount"] - 1), 0)
    positions.record_finish(key, marked)

    return {
        "markedRead": marked,
        "hardcoverError": result.get("error"),
        "moved": moved is not None,
        "movedTo": "books/read" if moved else None,
    }


@app.patch("/api/books/{key}")
def patch_book(key: str, body: MoveIn):
    """Move a book between books/available and books/read by hand."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    moved = library.move_book(key, body.finished)
    return {"moved": moved is not None, "finished": body.finished}


@app.delete("/api/books/{key}")
def remove_book(key: str):
    """Delete a summary. The source PDF, if there is one, stays in pdfs/."""
    if not library.delete_book(key):
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(key)
    enrich.forget(key)
    return {"deleted": True}


@app.get("/api/ingest/jobs")
def get_jobs():
    return {"jobs": jobs.list_jobs(), "hasKey": bool(os.environ.get("OPENAI_API_KEY"))}


@app.post("/api/ingest/upload")
async def upload(file: UploadFile = File(...), chunks: int | None = None):
    """Take a PDF and queue it for the pipeline."""
    name = file.filename or "book.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be ingested.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 200MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file is not a PDF.")

    return jobs.public(jobs.submit(name, data, chunks))


@app.delete("/api/ingest/jobs")
def clear_jobs():
    """Clear finished and failed jobs from the list; the books they made are kept."""
    return {"cleared": jobs.clear_finished()}


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
